package turnpike;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Models a toll plaza / booth on the Pennsylvania Turnpike.
 * Cars wait in a FIFO queue to be processed.
 *
 * <p>Added for the visualizer: a milepost (so the plaza can be placed on the
 * map), the car currently in the booth, and a count of cars that exited here.
 */
public class TollPlaza {
    private final String name;
    private final double milepost;
    private final ConcurrentLinkedQueue<Car> waitingCars;   // FIFO queue
    private final AtomicInteger carsProcessed;
    private final AtomicInteger carsExited;
    private final AtomicInteger totalTollCents;
    private volatile Car carInBooth;
    private volatile boolean open;

    public TollPlaza(String name) {
        this(name, 0);
    }

    public TollPlaza(String name, double milepost) {
        this.name = name;
        this.milepost = milepost;
        this.waitingCars = new ConcurrentLinkedQueue<>();
        this.carsProcessed = new AtomicInteger(0);
        this.carsExited = new AtomicInteger(0);
        this.totalTollCents = new AtomicInteger(0);
        this.open = true;
    }

    public String getName() {
        return name;
    }

    public double getMilepost() {
        return milepost;
    }

    public void enqueueCar(Car car) {
        if (open) {
            car.setStatus(Car.Status.QUEUED);
            waitingCars.offer(car);
            System.out.printf("[%s] [Car] %s joined the queue (queue size: %d)%n",
                    name, car.getLicensePlate(), waitingCars.size());
        }
    }

    public Car dequeueCar() {
        return waitingCars.poll();
    }

    public int getQueueSize() {
        return waitingCars.size();
    }

    /** Copy of the queue, front first. Safe to call while other threads use the queue. */
    public List<Car> snapshotQueue() {
        return new ArrayList<>(waitingCars);
    }

    public int getCarsProcessed() {
        return carsProcessed.get();
    }

    public void incrementProcessed() {
        carsProcessed.incrementAndGet();
    }

    public void addToll(double amount) {
        totalTollCents.addAndGet((int) Math.round(amount * 100));
    }

    public double getTotalTolls() {
        return totalTollCents.get() / 100.0;
    }

    public int getCarsExited() {
        return carsExited.get();
    }

    public void incrementExited() {
        carsExited.incrementAndGet();
    }

    public Car getCarInBooth() {
        return carInBooth;
    }

    public void setCarInBooth(Car car) {
        this.carInBooth = car;
    }

    public boolean isOpen() {
        return open;
    }

    public void close() {
        this.open = false;
    }

    @Override
    public String toString() {
        return String.format("TollPlaza[%s | MP %.0f | queue=%d | processed=%d]",
                name, milepost, getQueueSize(), getCarsProcessed());
    }
}
