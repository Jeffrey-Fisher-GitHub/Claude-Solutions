package turnpike;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Tracks cars driving between plazas. A car's trip time is proportional to the
 * miles between its entry and exit plaza, so long trips take longer on screen.
 */
public class TurnpikeTraffic {

    private final Map<String, TollPlaza> plazasByName = new HashMap<>();
    private final List<Car> traveling = new CopyOnWriteArrayList<>();
    private final List<Car> recentlyExited = new CopyOnWriteArrayList<>();
    private final AtomicInteger exitedTotal = new AtomicInteger();
    private final double msPerMile;

    public TurnpikeTraffic(List<TollPlaza> plazas, double msPerMile) {
        for (TollPlaza p : plazas) {
            plazasByName.put(p.getName(), p);
        }
        this.msPerMile = msPerMile;
    }

    /** A car finished paying at its entry booth and is now on the road. */
    public void depart(Car car) {
        double miles = milesBetween(car.getEntryPlaza(), car.getExitPlaza());
        car.startTrip(System.currentTimeMillis(), (long) (miles * msPerMile));
        traveling.add(car);
    }

    public double milesBetween(String fromPlaza, String toPlaza) {
        TollPlaza a = plazasByName.get(fromPlaza);
        TollPlaza b = plazasByName.get(toPlaza);
        if (a == null || b == null) {
            return 0;
        }
        return Math.abs(a.getMilepost() - b.getMilepost());
    }

    /** Moves finished trips to their exit plaza. Call this regularly (the engine does every 100 ms). */
    public void update(long nowMs) {
        List<Car> arrived = new ArrayList<>();
        for (Car c : traveling) {
            if (c.tripProgress(nowMs) >= 1.0) {
                arrived.add(c);
            }
        }
        for (Car c : arrived) {
            traveling.remove(c);
            c.setStatus(Car.Status.EXITED);
            TollPlaza exit = plazasByName.get(c.getExitPlaza());
            if (exit != null) {
                exit.incrementExited();
            }
            exitedTotal.incrementAndGet();
            recentlyExited.add(0, c);
            while (recentlyExited.size() > 12) {
                recentlyExited.remove(recentlyExited.size() - 1);
            }
        }
    }

    public List<Car> getTraveling() {
        return List.copyOf(traveling);
    }

    public List<Car> getRecentlyExited() {
        return List.copyOf(recentlyExited);
    }

    public int getExitedTotal() {
        return exitedTotal.get();
    }

    public boolean isEmpty() {
        return traveling.isEmpty();
    }
}
