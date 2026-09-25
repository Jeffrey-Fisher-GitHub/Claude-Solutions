package turnpike;

import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

/**
 * One direction of road between two neighboring interchanges, e.g. EB T326 Valley Forge -> T333 Norristown.
 *
 * The vehicles on the segment are kept in a bounded LinkedBlockingQueue: first in, first out,
 * no passing. The bound is the "jam" capacity (190 pc/mi/ln): once it is full, offer() returns false and
 * traffic backs up into the segment upstream, which is exactly how a real queue spills back.
 *
 * Several threads PUT vehicles into a segment (the upstream segment's worker and the entrance thread of
 * the interchange at its start). Exactly ONE thread (its SegmentWorker) takes vehicles OUT.
 */
public final class Segment {
    public final Interchange from;
    public final Interchange to;
    public final String direction;          // EB, WB, NB, SB
    public final double miles;
    public final int lanes;

    private final LinkedBlockingQueue<Vehicle> vehicles;

    // Live counts, updated by several threads at once, so they must be atomic.
    private final AtomicInteger cars = new AtomicInteger();
    private final AtomicInteger trucks = new AtomicInteger();
    private final AtomicLong enteredTotal = new AtomicLong();

    // A deliberately UNSAFE counter, bumped by the same threads with a plain ++.
    // At the end, compare it to enteredTotal to see "lost updates" (a race condition).
    long enteredUnsafe = 0;

    // Stats written ONLY by the Reporter thread (a single writer), then read after it shuts down.
    double peakDensity = 0;
    double minSpeed = TrafficModel.FFS;
    int samples = 0;
    int slowedSamples = 0;

    /** How many times a vehicle could not get in because this segment was jammed full (spillback). */
    final AtomicLong blockedAttempts = new AtomicLong();

    public Segment(Interchange from, Interchange to, String direction, double miles, int lanes) {
        this.from = from;
        this.to = to;
        this.direction = direction;
        this.miles = miles;
        this.lanes = lanes;
        int jamVehicles = (int) Math.max(4, TrafficModel.D_JAM * miles * lanes / 1.2);
        this.vehicles = new LinkedBlockingQueue<>(jamVehicles);
    }

    public String label() { return from.id + ">" + to.id; }

    /** Current density in passenger cars per mile per lane. */
    public double density() {
        return (cars.get() + TrafficModel.TRUCK_PCE * trucks.get()) / (miles * lanes);
    }

    public double speed() { return TrafficModel.speedForDensity(density()); }

    public int carCount()   { return cars.get(); }
    public int truckCount() { return trucks.get(); }
    public int vehicleCount() { return cars.get() + trucks.get(); }
    public long enteredTotal() { return enteredTotal.get(); }

    /**
     * Try to drive vehicle v onto this segment. Called by OTHER threads (producers).
     * @return false if the segment is jammed full (the caller must keep the vehicle and retry)
     */
    boolean tryEnter(Vehicle v, double simNow) {
        // TODO 3 (Thread-safe handoff). Several producer threads call this at the same time.
        //   a) set v.milesLeft = miles
        //   b) increment the right AtomicInteger (trucks or cars)
        //   c) push(label()) onto v.tripLog. Do this BEFORE offer(). Why? (after offer another thread owns v)
        //   d) vehicles.offer(v). It does NOT block; it returns false if the segment is full.
        //      If false: undo b) and c), increment blockedAttempts, return false.
        //   e) on success: enteredTotal.incrementAndGet(); enteredUnsafe++; return true
        //   Question: why use offer() here and not put()? What would put() do to the calling thread?
        return false;
    }

    /**
     * Only the SegmentWorker calls these. Iterating a LinkedBlockingQueue while other threads offer() is
     * safe: its iterator is "weakly consistent" (never throws ConcurrentModificationException).
     */
    Iterable<Vehicle> vehiclesOnRoad() { return vehicles; }

    Vehicle peekHead() { return vehicles.peek(); }

    Vehicle removeHead() {
        Vehicle v = vehicles.poll();
        if (v != null) (v.truck ? trucks : cars).decrementAndGet();
        return v;
    }
}
