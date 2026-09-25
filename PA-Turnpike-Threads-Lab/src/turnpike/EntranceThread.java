package turnpike;

import java.util.List;
import java.util.Random;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicLong;

/**
 * PRODUCER thread: one per interchange. Vehicles arrive at the toll plaza at random (a Poisson process)
 * at a rate set by that interchange's real 2023 entry AADT, and are trucks with the interchange's real
 * truck percentage. Each vehicle picks an exit and waits in the plaza queue until it can merge.
 *
 * This class implements Runnable instead of extending Thread, to show the other way to create a thread:
 *     new Thread(new EntranceThread(...), "entry-T326").start();
 */
public final class EntranceThread implements Runnable {
    private static final AtomicLong NEXT_ID = new AtomicLong(1);   // shared by all entrances: atomic

    private final Interchange home;
    private final RoadNetwork net;
    private final SimClock clock;
    private final Random rng;                 // one Random per thread: no contention, repeatable with a seed
    private final double arrivalsPerSimSecond;

    // Vehicles that have paid/tapped E-ZPass but can't merge yet. Read by the Reporter, so it is concurrent.
    final ConcurrentLinkedQueue<Vehicle> plaza = new ConcurrentLinkedQueue<>();

    private final Interchange[] exits;
    private final double[] cumulativeWeight;

    public EntranceThread(Interchange home, RoadNetwork net, SimClock clock, long seed,
                          double peakHourFactor, double surge, double tripDecayMiles) {
        this.home = home;
        this.net = net;
        this.clock = clock;
        this.rng = new Random(seed);
        this.arrivalsPerSimSecond = home.entryAADT * peakHourFactor * surge / 3600.0;

        // Gravity model: a trip to exit j is more likely if j is busy (high exit AADT) and not too far.
        List<Interchange> all = net.interchanges;
        exits = new Interchange[all.size() - 1];
        cumulativeWeight = new double[exits.length];
        double sum = 0;
        int k = 0;
        for (Interchange ic : all) {
            if (ic == home) continue;
            double miles = net.tripMiles(home, ic);
            sum += ic.exitAADT * Math.exp(-miles / tripDecayMiles);
            exits[k] = ic;
            cumulativeWeight[k++] = sum;
        }
    }

    public double arrivalsPerSimHour() { return arrivalsPerSimSecond * 3600; }

    /** Average trip length (miles) this entrance's gravity model will produce. */
    public double expectedTripMiles() {
        double sum = 0, prev = 0;
        for (int i = 0; i < exits.length; i++) {
            sum += (cumulativeWeight[i] - prev) * net.tripMiles(home, exits[i]);
            prev = cumulativeWeight[i];
        }
        return sum / cumulativeWeight[cumulativeWeight.length - 1];
    }

    private Interchange pickExit() {
        double r = rng.nextDouble() * cumulativeWeight[cumulativeWeight.length - 1];
        for (int i = 0; i < cumulativeWeight.length; i++) {
            if (r <= cumulativeWeight[i]) return exits[i];
        }
        return exits[exits.length - 1];
    }

    @Override
    public void run() {
        double nextArrival = clock.now() + expGap();
        try {
            while (!Thread.currentThread().isInterrupted()) {
                double now = clock.now();

                // 1) PRODUCE every vehicle whose arrival time has come.
                while (nextArrival <= now) {
                    boolean truck = rng.nextInt(100) < home.pctTrucks;
                    Vehicle v = new Vehicle(NEXT_ID.getAndIncrement(), truck, home, pickExit(), nextArrival);
                    for (Segment s : net.route(home, v.exit)) v.route.offer(s);   // enqueue the itinerary
                    plaza.offer(v);
                    nextArrival += expGap();
                }

                // 2) MERGE: move plaza vehicles onto their first segment until one is refused.
                Vehicle head;
                while ((head = plaza.peek()) != null) {
                    Segment first = head.route.poll();
                    if (first == null) { plaza.poll(); continue; }   // empty itinerary: nothing to drive
                    if (first.tryEnter(head, now)) {
                        plaza.poll();
                    } else {
                        head.route.addFirst(first);     // road is jammed: wait at the plaza
                        break;
                    }
                }

                clock.sleepSim(Math.min(Math.max(nextArrival - now, 0.1), clock.timeScale() * 0.02));
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    /** Exponential gap between Poisson arrivals, in simulated seconds. */
    private double expGap() {
        return -Math.log(1.0 - rng.nextDouble()) / arrivalsPerSimSecond;
    }

    public Interchange home() { return home; }
}
