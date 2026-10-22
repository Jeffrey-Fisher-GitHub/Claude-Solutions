package turnpike;

import java.util.Random;

/**
 * Worker thread that processes cars from a TollPlaza's FIFO queue.
 * Calculates a simple toll and records the transaction on the shared LIFO stack.
 *
 * <p>Added for the visualizer: the car in the booth is published on the plaza,
 * and when processing is done the car is handed to {@link TurnpikeTraffic},
 * which drives it toward its exit plaza.
 */
public class TollBoothOperatorThread extends Thread {
    private final TollPlaza plaza;
    private final TollTransactionHistory history;
    private final TurnpikeTraffic traffic;     // may be null (console-only mode)
    private final Random random = new Random();
    private volatile boolean running = true;

    // Simple distance / rate model (illustrative only)
    private static final double BASE_TOLL = 2.50;
    private static final double PER_SEGMENT = 1.75;

    public TollBoothOperatorThread(String name, TollPlaza plaza, TollTransactionHistory history) {
        this(name, plaza, history, null);
    }

    public TollBoothOperatorThread(String name, TollPlaza plaza, TollTransactionHistory history,
                                   TurnpikeTraffic traffic) {
        super(name);
        this.plaza = plaza;
        this.history = history;
        this.traffic = traffic;
        setDaemon(true);
    }

    @Override
    public void run() {
        System.out.printf("[OPEN] %s opened at %s%n", getName(), plaza.getName());

        while (running) {
            try {
                Car car = plaza.dequeueCar();
                if (car == null) {
                    // No car waiting - brief pause
                    Thread.sleep(150);
                    continue;
                }

                car.setStatus(Car.Status.AT_BOOTH);
                plaza.setCarInBooth(car);

                // Simulate processing time (cash takes longer than E-ZPass)
                int processMs = car.hasEZPass() ? 80 + random.nextInt(70)
                                                : 250 + random.nextInt(200);
                Thread.sleep(processMs);

                // Calculate a pretend toll
                double toll = calculateToll(car);
                car.setTollAmount(toll);

                plaza.incrementProcessed();
                plaza.addToll(toll);
                plaza.setCarInBooth(null);

                String record = String.format("%s processed %s  ->  $%.2f  (%s)",
                        plaza.getName(),
                        car.getLicensePlate(),
                        toll,
                        car.hasEZPass() ? "E-ZPass" : "Toll-by-Plate");

                history.push(record);

                if (traffic != null) {
                    traffic.depart(car);          // start driving to the exit plaza
                }

                System.out.printf("[OK] [%s] Processed %s  |  Toll: $%.2f  |  Queue left: %d%n",
                        plaza.getName(),
                        car.getLicensePlate(),
                        toll,
                        plaza.getQueueSize());

            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                break;
            }
        }

        plaza.setCarInBooth(null);
        System.out.printf("[CLOSE] %s closed at %s%n", getName(), plaza.getName());
    }

    private double calculateToll(Car car) {
        // Very simplified: base + random segments between entry and exit
        int segments = 1 + random.nextInt(8);
        double amount = BASE_TOLL + (segments * PER_SEGMENT);

        // E-ZPass discount (roughly half in real life on PA Turnpike)
        if (car.hasEZPass()) {
            amount *= 0.55;
        }
        return Math.round(amount * 100.0) / 100.0;
    }

    /** True while a car is being served or still waiting at this operator's plaza. */
    public boolean isBusy() {
        return plaza.getCarInBooth() != null || plaza.getQueueSize() > 0;
    }

    public void shutdown() {
        running = false;
        this.interrupt();
    }
}
