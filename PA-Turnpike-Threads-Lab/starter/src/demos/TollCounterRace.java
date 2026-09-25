package demos;

import java.util.concurrent.atomic.AtomicLong;

/**
 * WARM-UP (15 minutes): why do shared counters need protection?
 *
 * Eight toll-booth threads each count 1,000,000 vehicles into the SAME counters.
 * The correct total is always 8,000,000.
 *
 *   javac -d out src/demos/TollCounterRace.java
 *   java -cp out demos.TollCounterRace
 *
 * Expected: the plain long loses updates (and gives a different wrong answer each run); the synchronized
 * and AtomicLong counters are always right. Then ask students:
 *   - Why is count++ not one step? (read, add 1, write: another thread can sneak in between)
 *   - Which fix is faster, and why? (time them)
 */
public class TollCounterRace {
    static final int BOOTHS = 8;
    static final int CARS_PER_BOOTH = 1_000_000;

    static long unsafeCount = 0;                         // BROKEN: plain field, plain ++

    static long syncCount = 0;                           // FIX 1: guard with a lock
    static final Object LOCK = new Object();

    static final AtomicLong atomicCount = new AtomicLong();   // FIX 2: lock-free atomic

    public static void main(String[] args) throws InterruptedException {
        Thread[] booths = new Thread[BOOTHS];
        long start = System.nanoTime();
        for (int b = 0; b < BOOTHS; b++) {
            booths[b] = new Thread(() -> {
                for (int i = 0; i < CARS_PER_BOOTH; i++) {
                    unsafeCount++;
                    synchronized (LOCK) { syncCount++; }
                    atomicCount.incrementAndGet();
                }
            }, "booth-" + b);
            booths[b].start();
        }
        for (Thread t : booths) t.join();   // wait for every booth. Without join() we'd print too early.
        long ms = (System.nanoTime() - start) / 1_000_000;

        long expected = (long) BOOTHS * CARS_PER_BOOTH;
        System.out.printf("Expected       %,d%n", expected);
        System.out.printf("plain long++   %,d   (lost %,d updates)%n", unsafeCount, expected - unsafeCount);
        System.out.printf("synchronized   %,d%n", syncCount);
        System.out.printf("AtomicLong     %,d%n", atomicCount.get());
        System.out.printf("(%d ms total)%n", ms);
    }
}
