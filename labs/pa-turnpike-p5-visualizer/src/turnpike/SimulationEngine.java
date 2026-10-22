package turnpike;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Owns one run of the multi-threaded toll simulation and turns its live state
 * into JSON for the p5.js page.
 *
 * <pre>
 * IDLE --run--> RUNNING --producers done--> DRAINING --all cars exited--> FINISHED
 *   ^              |                            |
 *   +----reset-----+------------stop------------+---> STOPPED
 * </pre>
 */
public class SimulationEngine {

    /** Lifecycle of a run. */
    public enum State { IDLE, RUNNING, DRAINING, FINISHED, STOPPED }

    /** Milliseconds of animation per mile of Turnpike (about 9 s end to end). */
    static final double MS_PER_MILE = 25;

    private List<TollPlaza> plazas;
    private TollTransactionHistory history;
    private TurnpikeTraffic traffic;
    private final List<TollBoothOperatorThread> operators = new ArrayList<>();
    private final List<CarProducerThread> producers = new ArrayList<>();
    private Thread monitor;
    private volatile State state = State.IDLE;
    private long startedAtMs;
    private long finishedAtMs;
    private int carsRequested;
    private boolean rushHour;

    public SimulationEngine() {
        resetData();
    }

    public State getState() {
        return state;
    }

    private void resetData() {
        plazas = TurnpikeData.createPlazas();
        history = new TollTransactionHistory(50);
        traffic = new TurnpikeTraffic(plazas, MS_PER_MILE);
        operators.clear();
        producers.clear();
        startedAtMs = 0;
        finishedAtMs = 0;
        carsRequested = 0;
    }

    /**
     * Starts a run. {@code totalCars} is split across the three generators in the
     * same proportions as the original console simulation (18 / 22 / 12).
     * In rush hour, cars arrive five times as often, so booth queues build up.
     */
    public synchronized void start(int totalCars, boolean rushHour) {
        if (state == State.RUNNING || state == State.DRAINING) {
            return;
        }
        stopThreads();
        resetData();
        int west = Math.max(1, Math.round(totalCars * 18 / 52f));
        int east = Math.max(1, Math.round(totalCars * 22 / 52f));
        int local = Math.max(1, totalCars - west - east);
        carsRequested = west + east + local;
        this.rushHour = rushHour;
        double scale = rushHour ? 0.2 : 1.0;

        for (TollPlaza plaza : plazas) {
            TollBoothOperatorThread op = new TollBoothOperatorThread(
                    "Operator-" + plaza.getName().split(" ")[0], plaza, history, traffic);
            operators.add(op);
        }
        producers.add(new CarProducerThread("Westbound-Generator", plazas, west, scale));
        producers.add(new CarProducerThread("Eastbound-Generator", plazas, east, scale));
        producers.add(new CarProducerThread("Local-Traffic-Generator", plazas, local, scale));

        startedAtMs = System.currentTimeMillis();
        state = State.RUNNING;
        operators.forEach(Thread::start);
        producers.forEach(Thread::start);

        monitor = new Thread(this::monitorLoop, "Simulation-Monitor");
        monitor.setDaemon(true);
        monitor.start();
    }

    private void monitorLoop() {
        while (state == State.RUNNING || state == State.DRAINING) {
            traffic.update(System.currentTimeMillis());
            boolean producing = producers.stream().anyMatch(Thread::isAlive);
            if (!producing && state == State.RUNNING) {
                state = State.DRAINING;
                System.out.println("[INFO] All cars generated - draining queues and roads...");
            }
            boolean busy = operators.stream().anyMatch(TollBoothOperatorThread::isBusy);
            if (!producing && !busy && traffic.isEmpty()) {
                finish(State.FINISHED);
                return;
            }
            try {
                Thread.sleep(100);
            } catch (InterruptedException e) {
                return;
            }
        }
    }

    private synchronized void finish(State end) {
        if (state != State.RUNNING && state != State.DRAINING) {
            return;
        }
        state = end;
        finishedAtMs = System.currentTimeMillis();
        for (TollBoothOperatorThread op : operators) {
            op.shutdown();
        }
        System.out.printf("[INFO] Simulation %s. %d transactions on the LIFO stack.%n",
                end == State.FINISHED ? "complete" : "stopped", history.size());
        if (end == State.FINISHED) {
            history.printRecent(12);
        }
    }

    /** Stops a run early and freezes the picture where it is. */
    public synchronized void stop() {
        if (state == State.RUNNING || state == State.DRAINING) {
            producers.forEach(CarProducerThread::shutdown);
            finish(State.STOPPED);
            if (monitor != null) {
                monitor.interrupt();
            }
        }
    }

    /** Back to the static view with empty plazas. */
    public synchronized void reset() {
        stop();
        stopThreads();
        resetData();
        state = State.IDLE;
    }

    private void stopThreads() {
        producers.forEach(CarProducerThread::shutdown);
        operators.forEach(TollBoothOperatorThread::shutdown);
    }

    /** Everything the browser needs to draw one frame, as JSON. */
    public synchronized String snapshotJson() {
        long now = System.currentTimeMillis();
        Map<String, Object> root = new LinkedHashMap<>();
        root.put("serverTimeMs", now);
        root.put("state", state);
        root.put("msPerMile", MS_PER_MILE);
        root.put("mainlineMiles", TurnpikeData.MAINLINE_MILES);
        root.put("elapsedMs", startedAtMs == 0 ? 0 : (finishedAtMs > 0 ? finishedAtMs : now) - startedAtMs);
        root.put("carsRequested", carsRequested);
        root.put("rushHour", rushHour);

        List<Object> plazaList = new ArrayList<>();
        int queued = 0;
        int processed = 0;
        double revenue = 0;
        for (TollPlaza p : plazas) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("name", p.getName());
            m.put("milepost", p.getMilepost());
            m.put("region", TurnpikeData.regionOf(p.getName()));
            m.put("queueSize", p.getQueueSize());
            m.put("processed", p.getCarsProcessed());
            m.put("exited", p.getCarsExited());
            m.put("tolls", p.getTotalTolls());
            List<Object> q = new ArrayList<>();
            for (Car c : p.snapshotQueue()) {
                q.add(carJson(c, now));
            }
            m.put("queue", q);
            Car booth = p.getCarInBooth();
            m.put("inBooth", booth == null ? null : carJson(booth, now));
            plazaList.add(m);
            queued += p.getQueueSize();
            processed += p.getCarsProcessed();
            revenue += p.getTotalTolls();
        }
        root.put("plazas", plazaList);

        List<Object> moving = new ArrayList<>();
        for (Car c : traffic.getTraveling()) {
            moving.add(carJson(c, now));
        }
        root.put("traveling", moving);

        List<Object> exited = new ArrayList<>();
        for (Car c : traffic.getRecentlyExited()) {
            exited.add(carJson(c, now));
        }
        root.put("recentlyExited", exited);

        Map<String, Object> totals = new LinkedHashMap<>();
        totals.put("queued", queued);
        totals.put("processed", processed);
        totals.put("traveling", moving.size());
        totals.put("exited", traffic.getExitedTotal());
        totals.put("revenue", Math.round(revenue * 100) / 100.0);
        totals.put("stackSize", history.size());
        root.put("totals", totals);
        root.put("history", history.recent(15));
        return Json.write(root);
    }

    private Map<String, Object> carJson(Car c, long now) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", c.getId());
        m.put("plate", c.getLicensePlate());
        m.put("entry", c.getEntryPlaza());
        m.put("exit", c.getExitPlaza());
        m.put("ezpass", c.hasEZPass());
        m.put("status", c.getStatus());
        m.put("toll", c.getTollAmount());
        m.put("tripStartMs", c.getTripStartMs());
        m.put("tripDurationMs", c.getTripDurationMs());
        m.put("progress", c.tripProgress(now));
        return m;
    }
}
