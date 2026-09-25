package turnpike;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.DoubleAdder;

/** Completed trips. Every SegmentWorker writes here at once, so every field is thread-safe. */
public final class TripStats {
    final AtomicLong carsExited = new AtomicLong();
    final AtomicLong trucksExited = new AtomicLong();
    final DoubleAdder totalMinutes = new DoubleAdder();
    final DoubleAdder totalMiles = new DoubleAdder();
    final List<String> sampleDirections = new CopyOnWriteArrayList<>();

    private final RoadNetwork net;

    public TripStats(RoadNetwork net) { this.net = net; }

    void recordExit(Vehicle v, double simNow) {
        (v.truck ? trucksExited : carsExited).incrementAndGet();
        totalMinutes.add((simNow - v.departSimTime) / 60.0);
        totalMiles.add(net.tripMiles(v.entry, v.exit));
        // Check-then-act across threads: two workers can both see size()==4 and both add. Harmless here
        // (we might keep 6 samples), but it's a classic race. How would you make it exact?
        if (sampleDirections.size() < 5 && v.tripLog.size() >= 4) {
            String outbound = String.join(" | ", v.tripLog);    // bottom -> top, the order it was pushed
            sampleDirections.add(v + "\n      drove (stack bottom->top): " + outbound
                    + "\n      way home (pop order):      " + v.directionsHome());
        }
    }

    long exited() { return carsExited.get() + trucksExited.get(); }

    double avgMph() {
        double h = totalMinutes.sum() / 60.0;
        return h == 0 ? 0 : totalMiles.sum() / h;
    }
}
