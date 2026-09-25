package turnpike;

/**
 * CONSUMER thread: one per Segment.
 *
 * This is a "queue model" of the kind used by agent-based traffic simulators such as MATSim.
 * Every "tick" (about 10 ms of real time) it:
 *   1. measures density and looks up the HCM speed. Drivers slow from 70 mph (at 17 pc/mi/ln) toward 53 mph
 *      (at 45 pc/mi/ln, capacity).
 *   2. moves every vehicle forward by  speed * elapsed time
 *   3. releases vehicles from the HEAD of the FIFO queue that have reached the far end, moving each one
 *      into its next segment (or off the turnpike at its exit)
 *
 * Step 3 is limited by capacity (2,400 passenger cars per hour per lane). If more traffic arrives than a
 * segment can discharge, finished vehicles pile up at the head. That is a bottleneck queue: density goes past
 * 45 (LOS F) and the average speed falls far below 53 mph, even though the front still drains at capacity.
 *
 * Because the worker only releases the HEAD, nobody passes. A vehicle stuck at the front (its next
 * segment is jammed) holds up everyone behind it. That is spillback.
 */
public final class SegmentWorker extends Thread {
    private static final long TICK_MS = 10;

    private final Segment seg;
    private final SimClock clock;
    private final TripStats stats;

    public SegmentWorker(Segment seg, SimClock clock, TripStats stats) {
        super("seg-" + seg.direction + "-" + seg.label());   // named threads show up in jstack / VisualVM
        this.seg = seg;
        this.clock = clock;
        this.stats = stats;
        setDaemon(true);
    }

    @Override
    public void run() {
        double last = clock.now();
        double dischargeBudget = 0;          // passenger-car equivalents allowed out this tick
        double capacityPerSecond = TrafficModel.CAPACITY * seg.lanes / 3600.0;
        try {
            while (!isInterrupted()) {
                Thread.sleep(TICK_MS);
                double now = clock.now();
                double dt = now - last;
                last = now;

                // 1 + 2: everyone drives at the speed the current density allows
                double milesThisTick = TrafficModel.movingSpeed(seg.density()) * dt / 3600.0;
                for (Vehicle v : seg.vehiclesOnRoad()) v.milesLeft -= milesThisTick;

                // 3: release finished vehicles from the head, up to capacity
                dischargeBudget = Math.min(dischargeBudget + capacityPerSecond * dt, seg.lanes * 2.0);
                Vehicle head;
                while ((head = seg.peekHead()) != null && head.milesLeft <= 0 && dischargeBudget >= head.pce()) {
                    Segment next = head.route.poll();               // Queue: next leg of the trip
                    if (next == null) {                             // this was the last leg: exit
                        seg.removeHead();
                        stats.recordExit(head, now);
                    } else if (next.tryEnter(head, now)) {          // handoff to the next thread
                        seg.removeHead();
                    } else {                                        // next segment is jammed full
                        head.route.addFirst(next);                  // put it back and try next tick
                        break;
                    }
                    dischargeBudget -= head.pce();
                }
            }
        } catch (InterruptedException e) {
            // Interrupt is the polite "please stop" signal. Restore the flag and let run() return.
            Thread.currentThread().interrupt();
        }
    }
}
