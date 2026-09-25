package turnpike;

import java.io.IOException;
import java.io.PrintWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * PA Turnpike traffic simulation: Threads, Queues and Stacks.
 *
 *   javac -d out $(find src -name "*.java")
 *   java -cp out turnpike.Main --hours 3 --surge 1.0
 *
 * Options (all optional):
 *   --data PATH       interchange CSV (default data/interchanges_2023.csv)
 *   --hours H         simulated hours to run (default 3)
 *   --scale S         simulated seconds per real second (default 120, so 1 real second = 2 sim minutes)
 *   --k K             peak-hour factor: share of daily traffic in the busiest hour (default 0.09)
 *   --surge X         demand multiplier. 1.0 = 2023 peak hour; try 1.25, 1.5, 2.0 to force congestion
 *   --decay MILES     trip-length decay for the gravity model (default 40 -> ~32-mile average trip)
 *   --report MIN      report every MIN simulated minutes (default 15)
 *   --top N           rows in the "worst segments" table (default 8)
 *   --seed N          random seed (default 213)
 */
public final class Main {

    public static void main(String[] args) throws Exception {
        String data = "data/interchanges_2023.csv";
        double hours = 3, scale = 120, k = 0.09, surge = 1.0, decay = 40, reportMin = 15;
        int top = 8;
        long seed = 213;
        for (int i = 0; i < args.length; i += 2) {
            String v = args[i + 1];
            switch (args[i]) {
                case "--data":   data = v; break;
                case "--hours":  hours = Double.parseDouble(v); break;
                case "--scale":  scale = Double.parseDouble(v); break;
                case "--k":      k = Double.parseDouble(v); break;
                case "--surge":  surge = Double.parseDouble(v); break;
                case "--decay":  decay = Double.parseDouble(v); break;
                case "--report": reportMin = Double.parseDouble(v); break;
                case "--top":    top = Integer.parseInt(v); break;
                case "--seed":   seed = Long.parseLong(v); break;
                default: throw new IllegalArgumentException("Unknown option " + args[i]);
            }
        }

        RoadNetwork net = RoadNetwork.load(Paths.get(data));
        SimClock clock = new SimClock(scale);
        TripStats stats = new TripStats(net);

        System.out.printf("PA Turnpike simulation: %d interchanges, %d directional segments%n",
                net.interchanges.size(), net.segments.size());
        System.out.printf("Peak-hour factor %.2f x surge %.2f | slowdown above %.1f pc/mi/ln, breakdown above %.0f "
                + "| %.1f sim hours at %.0fx speed (~%.0f real seconds)%n",
                k, surge, TrafficModel.D_SLOWDOWN, TrafficModel.D_CAPACITY, hours, scale, hours * 3600 / scale);

        // ---- 1. Start one CONSUMER thread per segment (extends Thread) ----
        List<SegmentWorker> workers = new ArrayList<>();
        for (Segment s : net.segments.values()) {
            SegmentWorker w = new SegmentWorker(s, clock, stats);
            workers.add(w);
            w.start();          // start() makes a new thread; calling run() directly would NOT
        }

        // ---- 2. Start one PRODUCER thread per interchange (implements Runnable) ----
        List<EntranceThread> entrances = new ArrayList<>();
        List<Thread> entranceThreads = new ArrayList<>();
        long idx = 0;
        double totalPerHour = 0, weightedMiles = 0;
        for (Interchange ic : net.interchanges) {
            EntranceThread e = new EntranceThread(ic, net, clock, seed + idx++, k, surge, decay);
            entrances.add(e);
            totalPerHour += e.arrivalsPerSimHour();
            weightedMiles += e.arrivalsPerSimHour() * e.expectedTripMiles();
            Thread t = new Thread(e, "entry-" + ic.id);
            t.setDaemon(true);
            entranceThreads.add(t);
            t.start();
        }
        System.out.printf("Demand: %,.0f vehicles per simulated hour entering the turnpike, average trip %.0f miles. "
                + "Threads started: %d%n", totalPerHour, weightedMiles / totalPerHour,
                workers.size() + entranceThreads.size());

        // ---- 3. A thread POOL runs the reporter on a timer ----
        Path outDir = Paths.get("output");
        Files.createDirectories(outDir);
        PrintWriter csv = new PrintWriter(Files.newBufferedWriter(outDir.resolve("segment_timeseries.csv")));
        csv.println("simSeconds,direction,from,to,miles,lanes,cars,trucks,density_pc_mi_ln,speed_mph,los");
        ScheduledExecutorService timer = Executors.newSingleThreadScheduledExecutor();
        long periodMs = (long) (reportMin * 60 / scale * 1000);
        timer.scheduleAtFixedRate(new Reporter(net, entrances, stats, clock, csv, top),
                periodMs, periodMs, TimeUnit.MILLISECONDS);

        // ---- 4. Let the main thread wait while the others work ----
        Thread.sleep((long) (hours * 3600 / scale * 1000));

        // ---- 5. Shut down cleanly: stop producers, then consumers, then the timer ----
        for (Thread t : entranceThreads) t.interrupt();
        for (Thread t : entranceThreads) t.join();
        for (SegmentWorker w : workers) w.interrupt();
        for (SegmentWorker w : workers) w.join();
        timer.shutdown();
        timer.awaitTermination(5, TimeUnit.SECONDS);   // after this, Reporter's writes are visible to us
        csv.close();

        finalReport(net, stats, entrances);
    }

    private static void finalReport(RoadNetwork net, TripStats stats, List<EntranceThread> entrances) {
        System.out.println("\n================ FINAL REPORT: vehicles between exits ================");
        String[] names = {"EASTBOUND (I-76/I-276, west -> east)", "WESTBOUND (I-76/I-276, east -> west)",
                "NORTHBOUND (I-476 NE Extension)", "SOUTHBOUND (I-476 NE Extension)"};
        String[] codes = {"EB", "WB", "NB", "SB"};
        int[] now = Reporter.countByDirection(net.segments.values());
        for (int d = 0; d < 4; d++) {
            List<Segment> segs = new ArrayList<>();
            for (Segment s : net.segments.values()) if (s.direction.equals(codes[d])) segs.add(s);
            if (d == 1 || d == 3) java.util.Collections.reverse(segs);   // list in driving order
            long passed = 0;
            for (Segment s : segs) passed += s.enteredTotal();
            System.out.printf("%n%s  now on road: %,d   segment entries: %,d%n", names[d], now[d], passed);
            System.out.println("  Segment                                           mi ln  now(car/trk)  "
                    + "entered  peak pc/mi/ln  min mph  peak LOS  %time slowed");
            for (Segment s : segs) {
                System.out.printf("  %-48s %4.0f %2d  %5d/%-5d %9d  %12.1f  %7.1f  %6c   %9.0f%%%n",
                        s.from + " -> " + s.to, s.miles, s.lanes, s.carCount(), s.truckCount(),
                        s.enteredTotal(), s.peakDensity, s.minSpeed, TrafficModel.levelOfService(s.peakDensity),
                        s.samples == 0 ? 0.0 : 100.0 * s.slowedSamples / s.samples);
            }
        }

        int waiting = 0;
        for (EntranceThread e : entrances) waiting += e.plaza.size();
        long safe = 0, unsafe = 0, blocked = 0;
        for (Segment s : net.segments.values()) {
            safe += s.enteredTotal();
            unsafe += s.enteredUnsafe;
            blocked += s.blockedAttempts.get();
        }
        System.out.printf("%nTrips completed: %,d cars + %,d trucks, average %.1f mph door to door "
                        + "(including plaza waits). Still waiting at plazas: %,d%n",
                stats.carsExited.get(), stats.trucksExited.get(), stats.avgMph(), waiting);
        System.out.printf("Spillback: %,d times a vehicle was refused because the segment ahead was full.%n", blocked);
        System.out.printf("RACE CONDITION CHECK: AtomicLong counted %,d segment entries; plain long++ counted %,d "
                + "(lost updates: %,d)%n", safe, unsafe, safe - unsafe);

        System.out.println("\nSTACK DEMO: a vehicle's trip log, pushed while driving and popped at the exit:");
        for (String s : stats.sampleDirections) System.out.println("  " + s);
        System.out.println("\nTime series written to output/segment_timeseries.csv");
    }
}
