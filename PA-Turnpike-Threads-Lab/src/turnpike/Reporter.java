package turnpike;

import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

/**
 * Runs on a ScheduledExecutorService (a thread pool that runs tasks on a timer). Every tick it:
 *   - counts vehicles between exits in each direction (EB / WB / NB / SB)
 *   - finds segments where density is past the HCM slowdown point
 *   - appends a row per segment to a CSV so students can chart it
 */
public final class Reporter implements Runnable {
    private final RoadNetwork net;
    private final List<EntranceThread> entrances;
    private final TripStats stats;
    private final SimClock clock;
    private final PrintWriter csv;
    private final int topN;

    public Reporter(RoadNetwork net, List<EntranceThread> entrances, TripStats stats,
                    SimClock clock, PrintWriter csv, int topN) {
        this.net = net;
        this.entrances = entrances;
        this.stats = stats;
        this.clock = clock;
        this.csv = csv;
        this.topN = topN;
    }

    static int[] countByDirection(Collection<Segment> segs) {
        int[] c = new int[4];   // EB, WB, NB, SB
        for (Segment s : segs) c[dirIndex(s.direction)] += s.vehicleCount();
        return c;
    }

    static int dirIndex(String d) {
        switch (d) { case "EB": return 0; case "WB": return 1; case "NB": return 2; default: return 3; }
    }

    @Override
    public void run() {
        try {
            tick();
        } catch (RuntimeException e) {
            // An uncaught exception would silently cancel a scheduled task forever. Always catch in timers.
            e.printStackTrace();
        }
    }

    private void tick() {
        double now = clock.now();
        int[] dir = countByDirection(net.segments.values());
        int waiting = 0;
        for (EntranceThread e : entrances) waiting += e.plaza.size();

        List<Segment> slowed = new ArrayList<>();
        for (Segment s : net.segments.values()) {
            double d = s.density();
            double mph = TrafficModel.speedForDensity(d);
            s.samples++;
            if (d > s.peakDensity) s.peakDensity = d;
            if (mph < s.minSpeed) s.minSpeed = mph;
            if (d > TrafficModel.D_SLOWDOWN) { s.slowedSamples++; slowed.add(s); }
            csv.printf("%.0f,%s,%s,%s,%.1f,%d,%d,%d,%.2f,%.1f,%c%n", now, s.direction, s.from.id, s.to.id,
                    s.miles, s.lanes, s.carCount(), s.truckCount(), d, mph, TrafficModel.levelOfService(d));
        }
        csv.flush();

        System.out.printf("%n[sim %s] between exits -> EB %,d | WB %,d | NB %,d | SB %,d   "
                        + "waiting at plazas %,d   exited %,d%n",
                SimClock.fmt(now), dir[0], dir[1], dir[2], dir[3], waiting, stats.exited());

        slowed.sort((a, b) -> Double.compare(b.density(), a.density()));
        if (slowed.isEmpty()) {
            System.out.println("   all segments free-flowing (density <= "
                    + String.format("%.1f", TrafficModel.D_SLOWDOWN) + " pc/mi/ln)");
            return;
        }
        System.out.printf("   %d directional segments SLOWING (density > %.1f pc/mi/ln). Worst %d:%n",
                slowed.size(), TrafficModel.D_SLOWDOWN, Math.min(topN, slowed.size()));
        System.out.println("   Dir Segment                                          mi ln   cars trucks  pc/mi/ln   mph LOS");
        for (int i = 0; i < Math.min(topN, slowed.size()); i++) printRow(slowed.get(i));
    }

    static void printRow(Segment s) {
        double d = s.density();
        System.out.printf("   %-3s %-48s %4.0f %2d %6d %6d %9.1f %5.1f  %c%n",
                s.direction, s.from + " -> " + s.to, s.miles, s.lanes, s.carCount(), s.truckCount(),
                d, TrafficModel.speedForDensity(d), TrafficModel.levelOfService(d));
    }
}
