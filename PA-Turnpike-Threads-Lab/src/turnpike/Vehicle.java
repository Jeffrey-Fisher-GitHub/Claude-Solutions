package turnpike;

import java.util.ArrayDeque;
import java.util.Stack;

/**
 * A car or truck driving on the turnpike.
 *
 * DATA STRUCTURES ON DISPLAY
 *  - route   : a Queue (FIFO). The segments still ahead, in driving order. offer() at build time,
 *              poll() each time the vehicle moves into the next segment.
 *  - tripLog : a Stack (LIFO). Each segment is push()ed as the vehicle drives it. At the exit we
 *              pop() the stack, which gives back the segments in REVERSE order: the directions home.
 *
 * THREAD SAFETY
 *  A Vehicle is handed from one thread to another (entrance thread -> segment worker -> next segment
 *  worker...). Only ONE thread owns it at a time, and every handoff goes through a BlockingQueue.
 *  The BlockingQueue gives a "happens-before" guarantee: whatever the sender wrote before offer() is
 *  visible to the receiver after poll(). That is why route/tripLog/milesLeft need no locks.
 */
public final class Vehicle {
    public final long id;
    public final boolean truck;
    public final Interchange entry;
    public final Interchange exit;
    public final double departSimTime;

    // ArrayDeque implements Queue. We use Queue methods (offer/poll/peek) everywhere except one addFirst()
    // in SegmentWorker, which "un-polls" a segment when the vehicle can't get in yet.
    final ArrayDeque<Segment> route = new ArrayDeque<>();
    final Stack<String> tripLog = new Stack<>();

    /** Miles still to drive on the current segment. Set by the producer, then updated only by the owning worker. */
    double milesLeft;

    public Vehicle(long id, boolean truck, Interchange entry, Interchange exit, double departSimTime) {
        this.id = id;
        this.truck = truck;
        this.entry = entry;
        this.exit = exit;
        this.departSimTime = departSimTime;
    }

    /** Passenger-car equivalents: a truck takes up the road space of TRUCK_PCE cars. */
    public double pce() { return truck ? TrafficModel.TRUCK_PCE : 1.0; }

    /** Pop the trip log to produce the reverse route, e.g. "T333 <- A20 <- T339". */
    public String directionsHome() {
        StringBuilder sb = new StringBuilder(exit.id);
        while (!tripLog.isEmpty()) {
            String seg = tripLog.pop();                 // LIFO: last segment driven comes out first
            sb.append(" -> ").append(seg.substring(0, seg.indexOf('>')));
        }
        return sb.toString();
    }

    @Override
    public String toString() {
        return (truck ? "Truck#" : "Car#") + id + " " + entry.id + "->" + exit.id;
    }
}
