package turnpike;

import java.util.ArrayList;
import java.util.List;

/**
 * Main simulation of the Pennsylvania Turnpike demonstrating:
 *   - Threads          (CarProducerThread + TollBoothOperatorThread)
 *   - Queues (FIFO)    (ConcurrentLinkedQueue inside each TollPlaza)
 *   - Stacks (LIFO)    (ArrayDeque in TollTransactionHistory)
 *
 * Real plaza names from the PA Turnpike are used for flavor.
 * This is the original console version; for the p5.js picture run
 * {@link TurnpikeVisualizerServer} instead.
 */
public class PennsylvaniaTurnpikeSimulation {

    public static void main(String[] args) throws InterruptedException {
        System.out.println("=══════════════════════════════════════════════════════════════=");
        System.out.println("|     Pennsylvania Turnpike - Multi-Threaded Toll Simulation   |");
        System.out.println("|     (Threads + FIFO Queues + LIFO Transaction Stack)         |");
        System.out.println("=══════════════════════════════════════════════════════════════=\n");

        // ---- 1. Create real PA Turnpike plazas (now with mileposts) ----
        List<TollPlaza> plazas = TurnpikeData.createPlazas();

        // ---- 2. Shared LIFO history of recent transactions ----
        TollTransactionHistory history = new TollTransactionHistory(50);

        // ---- 3. Start operator threads (one per plaza) ----
        List<TollBoothOperatorThread> operators = new ArrayList<>();
        for (TollPlaza plaza : plazas) {
            TollBoothOperatorThread op = new TollBoothOperatorThread(
                    "Operator-" + plaza.getName().split(" ")[0],
                    plaza,
                    history);
            operators.add(op);
            op.start();
        }

        // ---- 4. Start several car-producer threads ----
        // Each thread spins up its own Car instances and sends them onto the Turnpike
        List<CarProducerThread> producers = new ArrayList<>();
        producers.add(new CarProducerThread("Westbound-Generator", plazas, 18));
        producers.add(new CarProducerThread("Eastbound-Generator", plazas, 22));
        producers.add(new CarProducerThread("Local-Traffic-Generator", plazas, 12));

        for (CarProducerThread p : producers) {
            p.start();
        }

        // ---- 5. Let the simulation run for a while ----
        System.out.println("\n[WAIT] Simulation running for ~12 seconds...\n");
        Thread.sleep(12_000);

        // ---- 6. Graceful shutdown ----
        System.out.println("\n[INFO] Closing the Turnpike - stopping producers...");
        for (CarProducerThread p : producers) {
            p.shutdown();
        }
        for (CarProducerThread p : producers) {
            p.join(2000);
        }

        // Give operators a little more time to drain remaining queues
        System.out.println("[INFO] Allowing operators to finish remaining cars...");
        Thread.sleep(3000);

        for (TollBoothOperatorThread op : operators) {
            op.shutdown();
        }
        for (TollBoothOperatorThread op : operators) {
            op.join(2000);
        }

        // ---- 7. Final report ----
        printFinalReport(plazas, history);
    }

    private static void printFinalReport(List<TollPlaza> plazas, TollTransactionHistory history) {
        System.out.println("\n=══════════════════════════════════════════════════════════════=");
        System.out.println("|                    FINAL TURNPIKE REPORT                     |");
        System.out.println("=══════════════════════════════════════════════════════════════=");

        int totalProcessed = 0;
        int totalStillQueued = 0;

        System.out.println("\nToll Plaza Status:");
        for (TollPlaza p : plazas) {
            System.out.printf("  %-30s  processed=%3d  remaining-in-queue=%d%n",
                    p.getName(), p.getCarsProcessed(), p.getQueueSize());
            totalProcessed += p.getCarsProcessed();
            totalStillQueued += p.getQueueSize();
        }

        System.out.printf("%nTotal cars processed : %d%n", totalProcessed);
        System.out.printf("Cars left in queues  : %d%n", totalStillQueued);
        System.out.printf("Transactions on stack: %d%n", history.size());

        // Show the LIFO nature of the stack
        history.printRecent(12);

        System.out.println("Simulation complete. Drive safely on the PA Turnpike! [ROAD]");
    }
}
