# CISC 213 Lab: PA Turnpike Traffic Simulator
### Threads · Queues · Stacks

You will finish a multithreaded Java simulation of the Pennsylvania Turnpike. The simulation uses real 2023 traffic volumes and truck percentages. Your job is to add enough traffic to find where, and when, cars must **slow down between exits**. You will also count the vehicles between each pair of exits **Eastbound, Westbound, Northbound and Southbound**.

> **Why this matters now:** In January 2025 the PA Turnpike switched to *Open Road Tolling* east of Reading and on the Northeast Extension. Toll booths were replaced by overhead gantries **between interchanges**, which read E-ZPass or photograph plates at highway speed. The rest of the turnpike converts in 2027. Every segment in this lab is one of those "between-interchange" stretches. A real ORT back office is a set of concurrent producers (gantries) feeding queues of transactions to consumers (billing), which is exactly the pattern you will build.

---

## 1. The model

```
 entry-T326 (producer thread)                 seg-EB-T326>T333 (consumer thread)
 ┌──────────────┐  offer()   ┌───────────────────────────────┐  tryEnter()  ┌──────────────────┐
 │ plaza queue  │ ─────────► │ LinkedBlockingQueue<Vehicle>  │ ───────────► │ next segment ... │
 │ (waiting)    │            │ FIFO, bounded = jam density   │              └──────────────────┘
 └──────────────┘            └───────────────────────────────┘
                                   ▲ also fed by the upstream segment's thread

 Vehicle
   route   : Queue<Segment>  -> segments still ahead      (FIFO: poll the next leg)
   tripLog : Stack<String>   -> segments already driven   (LIFO: pop = directions home)
```

| Piece | Java concept | File |
|---|---|---|
| 43 interchanges, each with an **EntranceThread** (`implements Runnable`) | producer threads, `Random` per thread | `EntranceThread.java` |
| 84 directional segments, each with a **SegmentWorker** (`extends Thread`) | consumer threads, `interrupt()` shutdown | `SegmentWorker.java` |
| Vehicles on a segment | `LinkedBlockingQueue` (bounded, FIFO, thread-safe) | `Segment.java` |
| Live counts | `AtomicInteger`, `AtomicLong` vs. a plain `long++` | `Segment.java` |
| Route itinerary | `Queue` (`ArrayDeque`) | `Vehicle.java` |
| Trip log / directions home | `Stack` | `Vehicle.java` |
| Periodic report | `ScheduledExecutorService` (a thread pool) | `Reporter.java`, `Main.java` |
| Race-condition warm-up | `synchronized` vs `AtomicLong` vs `++` | `demos/TollCounterRace.java` |

### Real data (`data/interchanges_2023.csv`)
From the PA Turnpike Commission's **2023 Interchange AADT** report: daily entries, daily exits and **% trucks** for all 32 mainline interchanges (Gateway T2 → Delaware River Bridge) and the 11 Northeast Extension interchanges (Mid-County A20 → Clarks Summit A131). The interchange number is its milepost, so segment length = difference in mileposts.

> **Data-quality note:** in the published PDF, the Mid-County (A20) and Delaware River Bridge (H43) rows have *identical* numbers. We use them as published. Discuss: what would you do in production?

### The slowdown metric (Highway Capacity Manual, 6th ed.)
**Density** = passenger-car equivalents per mile per lane (pc/mi/ln). One truck = **2.0** passenger cars on level terrain.

| Density (pc/mi/ln) | LOS | What drivers experience |
|---|---|---|
| 0–11 | A | free flow, 70 mph |
| 11–17.1 | B | still 70 mph |
| **> 17.1** | C/D/E | **cars begin to slow down** (HCM speed-flow breakpoint) |
| 35–45 | E | ~53–59 mph, at capacity (2,400 pc/h/ln) |
| **> 45** | **F** | **breakdown**: a queue forms, stop-and-go |

Demand per interchange = `entry AADT × K × surge`, where **K = 0.09** is the share of daily traffic in the peak hour and **surge** is your knob. Trips choose an exit using a *gravity model* that favors busy, nearby exits (average trip ≈ 32 miles).

**Simplifications to keep in mind:** lane counts (3 lanes per direction east of Downingtown and south of Lansdale, 2 elsewhere), no passing within a segment, level terrain, and constant peak-hour demand. These are fair game for extensions.

---

## 2. Build & run

Java 8 or newer. From this folder:

```bash
javac -d out $(find src -name "*.java")          # Windows: see note below
java -cp out demos.TollCounterRace               # warm-up
java -cp out turnpike.Main --surge 1.0           # 3 simulated hours in ~90 real seconds
```

Windows (PowerShell): `javac -d out (Get-ChildItem -Recurse src -Filter *.java).FullName`

Useful options: `--hours 3  --scale 120  --surge 1.0  --k 0.09  --report 15  --top 8  --seed 213`

Output: a report every 15 simulated minutes, a final table of **every segment in every direction**, and `output/segment_timeseries.csv` for charting in Excel.

### Sample (solution, `--surge 1.25`, 30 minutes in)
```
[sim 00:30:15] between exits -> EB 7,009 | WB 6,071 | NB 1,056 | SB 2,838   waiting at plazas 0   exited 9,370
   22 directional segments SLOWING (density > 17.1 pc/mi/ln). Worst 6:
   Dir Segment                                          mi ln   cars trucks  pc/mi/ln   mph LOS
   WB  T351 Bensalem -> T343 Willow Grove                  8  3   1061    166      58.0  41.3  F
   EB  A20 Mid-County -> T339 Fort Washington              5  3    532     86      46.9  51.1  F
```

---

## 3. Your tasks (in `starter/src`)

Build the starter the same way (`javac -d out $(find starter/src -name "*.java")`). It compiles and runs, but no traffic moves until you finish the TODOs.

| # | File | Concept | What to write |
|---|---|---|---|
| 1 | `Vehicle.directionsHome()` | **Stack** | pop the trip log to produce the reverse route |
| 2 | `EntranceThread.run()` | **Queue** | `offer()` each segment of the route into the vehicle's itinerary |
| 3 | `Segment.tryEnter()` | **thread-safe handoff** | atomic counts, `push`, non-blocking `offer()`, undo on failure |
| 4 | `SegmentWorker.run()` | **consumer loop** | release head vehicles: exit, hand off, or spill back |
| 5 | `Reporter.countByDirection()` | **counting** | EB / WB / NB / SB vehicles between exits |

Check yourself: with `--surge 1.0`, the 00:30 report should show about 20 segments slowing, almost all around Philadelphia.

---

## 4. Experiments (answer in your write-up)

1. **Find the tipping point.** Run `--surge` at 0.75, 1.0, 1.25 and 1.5. For each, record: the number of segments with density > 17.1, the first segment to reach LOS F, and the simulated time it happened. Where does the turnpike break down first, and why there? (Hint: look at the lanes and at the interchange volumes.)
2. **Directional counts.** At surge 1.0, which direction has the most vehicles between exits after 3 hours? Explain the EB/WB and NB/SB imbalance from the data and the gravity model.
3. **Trucks.** Set every interchange's truck % to 0 (edit the CSV copy). How much does peak density drop? Why does a truck count as 2 cars?
4. **Race condition.** Run `demos.TollCounterRace` three times. Then compare `enteredUnsafe` with `enteredTotal` in the simulation's final report. Why does the demo lose tens of thousands of updates while the simulation loses almost none?
5. **Thread count.** How many threads does the program start? Use `jconsole` or `jstack <pid>` while it runs, and screenshot the named threads (`seg-EB-T326>T333`, `entry-T326`, …).

## 5. Extensions (pick one)
- **ORT tolls:** toll each segment at a per-mile rate plus a fixed per-gantry charge by popping the trip log. Trucks pay more.
- **Time of day:** replace the constant K with PennDOT's published hourly percentages so demand rises and falls.
- **Incident:** at 01:00 cut one segment to 1 lane for 20 minutes. Watch the spillback and the recovery.
- **ExecutorService:** replace the 84 `SegmentWorker` threads with a fixed pool of 8 workers that each tick a list of segments. What changes?
- **Deque:** replace `Stack` with `ArrayDeque` as Oracle recommends, and explain why.

## 6. Deliverables
1. Your completed `starter/src` (zip or GitHub link)
2. A one-to-two-page write-up answering Experiments 1–5, with one chart made from `segment_timeseries.csv` (density over time for the three worst segments)
3. Screenshot of your final report at `--surge 1.25`

## References
- Oracle, [`Thread`](https://docs.oracle.com/javase/8/docs/api/java/lang/Thread.html), [Concurrency tutorial](https://docs.oracle.com/javase/tutorial/essential/concurrency/), [Multithreaded Programming Guide](https://docs.oracle.com/cd/E19455-01/806-5257/)
- Oracle, [`Stack`](https://docs.oracle.com/javase/8/docs/api/java/util/Stack.html), [`Queue`](https://docs.oracle.com/javase/8/docs/api/java/util/Queue.html), [Queue interface](https://docs.oracle.com/javase/tutorial/collections/interfaces/queue.html), [Queue implementations](https://docs.oracle.com/javase/tutorial/collections/implementations/queue.html)
- PA Turnpike Commission, [2023 Interchange AADT](https://files.paturnpike.com/production/docs/default-source/resources/traffic-reports/traffic-reports-2023/2023-interchange-aadt.pdf?sfvrsn=7d283d6c_5)
- PA Turnpike, [Open Road Tolling](https://www.paturnpike.com/all-electronic-tolling/open-road-tolling) and [2027 western launch](https://www.paturnpike.com/news/details/2025/12/16/pennsylvania-turnpike-begins-installing-tolling-equipment-on-newly-constructed-gantries-for-2027-launch)
- Highway Capacity Manual, 6th ed., basic freeway segments ([summary](https://www.cedengineering.com/userfiles/Highway%20Capacity%20Manual%20-%206th%20Edition%20Overview%20-%20R2.pdf)); LOS thresholds ([U. Memphis CIVL 3161 notes](https://www.ce.memphis.edu/3161/pdf%20files/Highway%20Capacity%20and%20LOS-%20class.pdf))
