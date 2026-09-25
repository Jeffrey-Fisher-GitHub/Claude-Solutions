package turnpike;

/**
 * Maps real (wall-clock) time to simulated time.
 * With timeScale = 60, one real second is one simulated minute.
 */
public final class SimClock {
    private final long startNanos = System.nanoTime();
    private final double timeScale;

    public SimClock(double timeScale) { this.timeScale = timeScale; }

    /** Simulated seconds since the simulation started. */
    public double now() {
        return (System.nanoTime() - startNanos) / 1e9 * timeScale;
    }

    /** Sleep the calling thread for the given number of simulated seconds. */
    public void sleepSim(double simSeconds) throws InterruptedException {
        long realMillis = (long) Math.max(1, simSeconds / timeScale * 1000);
        Thread.sleep(realMillis);
    }

    public double timeScale() { return timeScale; }

    public static String fmt(double simSeconds) {
        long s = (long) simSeconds;
        return String.format("%02d:%02d:%02d", s / 3600, (s / 60) % 60, s % 60);
    }
}
