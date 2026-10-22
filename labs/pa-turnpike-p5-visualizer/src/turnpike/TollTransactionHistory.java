package turnpike;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.Iterator;
import java.util.List;

/**
 * Shared LIFO stack of recent toll transactions. The newest record is always on
 * top. When the stack reaches capacity, the oldest record (the bottom) is
 * dropped. Methods are synchronized because many operator threads push at once.
 */
public class TollTransactionHistory {
    private final Deque<String> stack = new ArrayDeque<>();
    private final int capacity;
    private int totalPushed;

    public TollTransactionHistory(int capacity) {
        if (capacity < 1) {
            throw new IllegalArgumentException("capacity must be >= 1");
        }
        this.capacity = capacity;
    }

    public synchronized void push(String record) {
        stack.push(record);              // top of stack
        totalPushed++;
        if (stack.size() > capacity) {
            stack.removeLast();          // drop the oldest (bottom)
        }
    }

    public synchronized String pop() {
        return stack.poll();
    }

    public synchronized String peek() {
        return stack.peek();
    }

    public synchronized int size() {
        return stack.size();
    }

    /** All records pushed since creation, including ones dropped off the bottom. */
    public synchronized int getTotalPushed() {
        return totalPushed;
    }

    /** Up to {@code n} records, newest first (top of the stack first). */
    public synchronized List<String> recent(int n) {
        List<String> out = new ArrayList<>(Math.min(n, stack.size()));
        Iterator<String> it = stack.iterator();
        while (it.hasNext() && out.size() < n) {
            out.add(it.next());
        }
        return out;
    }

    public void printRecent(int n) {
        System.out.printf("%nMost recent %d transactions (LIFO - newest first):%n", n);
        int i = 1;
        for (String r : recent(n)) {
            System.out.printf("  %2d. %s%n", i++, r);
        }
        System.out.println();
    }
}
