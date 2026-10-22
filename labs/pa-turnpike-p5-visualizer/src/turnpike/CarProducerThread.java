package turnpike;

import java.util.List;
import java.util.Random;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Each instance of this thread "spins up" Car instances and sends them
 * onto the Pennsylvania Turnpike (i.e., enqueues them at their entry plaza).
 *
 * <p>Fix for the visualizer: the original version picked one random plaza to
 * put on the car's ticket and a <em>different</em> random plaza to enqueue the
 * car at. Now the car waits at the entry plaza named on its ticket, so the
 * drawing shows each car leaving from the right place.
 */
public class CarProducerThread extends Thread {
    private static final AtomicInteger plateCounter = new AtomicInteger(1000);
    private static final String[] PA_PLATES_PREFIX = {
            "PA", "PENN", "KEY", "STEEL", "LIBERTY"
    };

    private final List<TollPlaza> plazas;
    private final int carsToProduce;
    private final double arrivalScale;
    private final Random random = new Random();
    private volatile boolean running = true;

    public CarProducerThread(String name, List<TollPlaza> plazas, int carsToProduce) {
        this(name, plazas, carsToProduce, 1.0);
    }

    /**
     * @param arrivalScale multiplies the gap between arrivals: 1.0 is the original
     *                     timing, 0.2 is "rush hour" (cars arrive 5x as often, so queues form)
     */
    public CarProducerThread(String name, List<TollPlaza> plazas, int carsToProduce, double arrivalScale) {
        super(name);
        this.plazas = plazas;
        this.carsToProduce = carsToProduce;
        this.arrivalScale = arrivalScale;
        setDaemon(true);
    }

    @Override
    public void run() {
        System.out.printf("[START] %s started - will generate %d cars%n", getName(), carsToProduce);

        for (int i = 0; i < carsToProduce && running; i++) {
            try {
                // Simulate cars arriving at irregular intervals
                Thread.sleep(Math.round((200 + random.nextInt(400)) * arrivalScale));

                // Pick distinct entry / exit plazas
                TollPlaza entry = plazas.get(random.nextInt(plazas.size()));
                TollPlaza exit;
                do {
                    exit = plazas.get(random.nextInt(plazas.size()));
                } while (exit == entry && plazas.size() > 1);

                Car car = createRandomCar(entry, exit);
                entry.enqueueCar(car);

            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                break;
            }
        }

        System.out.printf("[DONE] %s finished producing cars%n", getName());
    }

    private Car createRandomCar(TollPlaza entryPlaza, TollPlaza exitPlaza) {
        String plate = PA_PLATES_PREFIX[random.nextInt(PA_PLATES_PREFIX.length)]
                + "-" + plateCounter.getAndIncrement();

        boolean hasEZPass = random.nextDouble() < 0.65; // ~65% E-ZPass usage

        return new Car(plate, entryPlaza.getName(), exitPlaza.getName(), hasEZPass);
    }

    public void shutdown() {
        running = false;
        this.interrupt();
    }
}
