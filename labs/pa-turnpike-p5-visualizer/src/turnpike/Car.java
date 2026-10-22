package turnpike;

import java.util.concurrent.atomic.AtomicInteger;

/**
 * Represents a vehicle traveling on the Pennsylvania Turnpike.
 *
 * <p>Added for the visualizer: an id, a {@link Status}, and trip timing, so the
 * browser can draw where each car is (queued at a booth, being served, or
 * driving toward its exit plaza).
 */
public class Car {

    /** Where the car is in its trip. */
    public enum Status { QUEUED, AT_BOOTH, TRAVELING, EXITED }

    private static final AtomicInteger NEXT_ID = new AtomicInteger(1);

    private final int id;
    private final String licensePlate;
    private final String entryPlaza;
    private final String exitPlaza;
    private final boolean hasEZPass;
    private final long arrivalTimeMs;
    private volatile double tollAmount;

    private volatile Status status = Status.QUEUED;
    private volatile long tripStartMs;
    private volatile long tripDurationMs;

    public Car(String licensePlate, String entryPlaza, String exitPlaza, boolean hasEZPass) {
        this.id = NEXT_ID.getAndIncrement();
        this.licensePlate = licensePlate;
        this.entryPlaza = entryPlaza;
        this.exitPlaza = exitPlaza;
        this.hasEZPass = hasEZPass;
        this.arrivalTimeMs = System.currentTimeMillis();
        this.tollAmount = 0.0;
    }

    public int getId() {
        return id;
    }

    public String getLicensePlate() {
        return licensePlate;
    }

    public String getEntryPlaza() {
        return entryPlaza;
    }

    public String getExitPlaza() {
        return exitPlaza;
    }

    public boolean hasEZPass() {
        return hasEZPass;
    }

    public long getArrivalTimeMs() {
        return arrivalTimeMs;
    }

    public double getTollAmount() {
        return tollAmount;
    }

    public void setTollAmount(double tollAmount) {
        this.tollAmount = tollAmount;
    }

    public Status getStatus() {
        return status;
    }

    public void setStatus(Status status) {
        this.status = status;
    }

    /** Called when the car leaves the entry booth and starts driving to its exit plaza. */
    public void startTrip(long startMs, long durationMs) {
        this.tripStartMs = startMs;
        this.tripDurationMs = Math.max(1, durationMs);
        this.status = Status.TRAVELING;
    }

    public long getTripStartMs() {
        return tripStartMs;
    }

    public long getTripDurationMs() {
        return tripDurationMs;
    }

    /** Fraction of the trip completed, 0.0 to 1.0. */
    public double tripProgress(long nowMs) {
        if (status != Status.TRAVELING) {
            return status == Status.EXITED ? 1.0 : 0.0;
        }
        return Math.min(1.0, (nowMs - tripStartMs) / (double) tripDurationMs);
    }

    @Override
    public String toString() {
        return String.format("Car[%s | %s -> %s | %s | $%.2f]",
                licensePlate,
                entryPlaza,
                exitPlaza,
                hasEZPass ? "E-ZPass" : "Toll-by-Plate",
                tollAmount);
    }
}
