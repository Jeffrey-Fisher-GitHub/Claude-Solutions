package turnpike;

/**
 * Speed/density math from the Highway Capacity Manual, 6th Edition (HCM6), basic freeway segments.
 *
 *   Density D (pc/mi/ln) = passenger-car equivalents on the segment / (miles * lanes)
 *   A truck counts as ET = 2.0 passenger cars on level terrain (HCM6; was 1.5 in HCM 2010).
 *
 *   FFS  = 70 mph free-flow speed
 *   c    = min(2200 + 10*(FFS-50), 2400)      = 2400 pc/h/ln capacity
 *   BP   = 1000 + 40*(75-FFS)                 = 1200 pc/h/ln breakpoint
 *   S(v) = FFS                                        for v <= BP
 *        = FFS - (FFS - c/45) * ((v-BP)/(c-BP))^2      for BP < v <= c
 *
 * So cars drive at 70 mph until density reaches BP/FFS = 17.1 pc/mi/ln (the end of LOS B). Above that
 * they start to SLOW DOWN, reaching 53.3 mph at capacity (45 pc/mi/ln, the LOS E/F boundary).
 * Past 45 the segment is broken down (LOS F): a queue has formed and drains at capacity, so the average
 * speed is roughly capacity / density (a teaching simplification, not an HCM formula). The jam density of
 * 190 pc/mi/ln sets how many vehicles fit on a segment before it refuses new ones.
 */
public final class TrafficModel {
    public static final double FFS = 70.0;
    public static final double CAPACITY = Math.min(2200 + 10 * (FFS - 50), 2400);   // pc/h/ln
    public static final double BREAKPOINT_FLOW = 1000 + 40 * (75 - FFS);           // pc/h/ln
    public static final double D_SLOWDOWN = BREAKPOINT_FLOW / FFS;                 // 17.1 pc/mi/ln
    public static final double D_CAPACITY = 45.0;                                  // pc/mi/ln
    public static final double D_JAM = 190.0;                                      // pc/mi/ln
    public static final double TRUCK_PCE = 2.0;
    public static final double MIN_SPEED = 3.0;                                    // mph, stop-and-go floor

    private TrafficModel() { }

    /** HCM6 speed for a given flow rate (undersaturated branch). */
    static double speedForFlow(double v) {
        if (v <= BREAKPOINT_FLOW) return FFS;
        double x = (v - BREAKPOINT_FLOW) / (CAPACITY - BREAKPOINT_FLOW);
        return FFS - (FFS - CAPACITY / D_CAPACITY) * x * x;
    }

    /** Speed (mph) that drivers choose at a given density (pc/mi/ln). */
    public static double speedForDensity(double d) {
        if (d <= D_SLOWDOWN) return FFS;
        if (d <= D_CAPACITY) {
            // Density v/S(v) rises steadily with v, so solve for v by bisection.
            double lo = BREAKPOINT_FLOW, hi = CAPACITY;
            for (int i = 0; i < 40; i++) {
                double mid = (lo + hi) / 2;
                if (mid / speedForFlow(mid) < d) lo = mid; else hi = mid;
            }
            return speedForFlow((lo + hi) / 2);
        }
        return Math.max(MIN_SPEED, CAPACITY / d);     // queue discharging at capacity
    }

    /** Speed a driver can actually hold while moving: HCM speed, never below the speed at capacity. */
    public static double movingSpeed(double d) {
        return speedForDensity(Math.min(d, D_CAPACITY));
    }

    /** HCM level of service letter for a basic freeway segment. */
    public static char levelOfService(double d) {
        if (d <= 11) return 'A';
        if (d <= 18) return 'B';
        if (d <= 26) return 'C';
        if (d <= 35) return 'D';
        if (d <= 45) return 'E';
        return 'F';
    }
}
