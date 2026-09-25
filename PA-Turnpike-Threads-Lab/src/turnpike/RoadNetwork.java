package turnpike;

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Builds the road: interchanges from the CSV plus a Segment for each direction between neighbors.
 *
 *   Mainline (I-76/I-276):     T2 Gateway ... T333 Norristown - A20 Mid-County - T339 ... H43   (EB / WB)
 *   Northeast Ext (I-476):     A20 Mid-County - A31 Lansdale ... A131 Clarks Summit             (NB / SB)
 *
 * The two roads meet at the Mid-County junction (A20), so a trip from Pittsburgh to Scranton runs EB to A20,
 * then NB.
 */
public final class RoadNetwork {
    public final List<Interchange> interchanges = new ArrayList<>();
    public final List<Interchange> mainline = new ArrayList<>();   // sorted west -> east
    public final List<Interchange> northeast = new ArrayList<>();  // sorted south -> north
    public final Map<String, Segment> segments = new LinkedHashMap<>();
    public Interchange junction;

    public static RoadNetwork load(Path csv) throws IOException {
        RoadNetwork net = new RoadNetwork();
        try (BufferedReader in = Files.newBufferedReader(csv, StandardCharsets.UTF_8)) {
            String line;
            boolean header = true;
            while ((line = in.readLine()) != null) {
                if (line.isEmpty() || line.startsWith("#")) continue;
                if (header) { header = false; continue; }
                String[] f = line.split(",");
                Interchange ic = new Interchange(f[0], f[1], f[2], Double.parseDouble(f[3]),
                        Integer.parseInt(f[4]), Integer.parseInt(f[5]), Integer.parseInt(f[6]));
                net.interchanges.add(ic);
                if (ic.isOnMainline()) net.mainline.add(ic);
                if (ic.isOnNortheast()) net.northeast.add(ic);
                if (ic.road.equals("JCT")) net.junction = ic;
            }
        }
        net.mainline.sort(Comparator.comparingDouble(Interchange::mlMilepost));
        net.northeast.sort(Comparator.comparingDouble(Interchange::neMilepost));
        net.buildSegments();
        return net;
    }

    /**
     * Lanes per direction. SIMPLIFIED on purpose. The eastern (Philadelphia-area) mainline and the south end
     * of the NE Extension have been widened to three lanes; most of the rest is two. Students can refine this.
     */
    static int lanesFor(String road, double fromMp, double toMp) {
        double lo = Math.min(fromMp, toMp);
        if (road.equals("ML")) return lo >= 312 ? 3 : 2;
        return lo < 31 ? 3 : 2;
    }

    private void buildSegments() {
        for (int i = 0; i + 1 < mainline.size(); i++) {
            Interchange w = mainline.get(i), e = mainline.get(i + 1);
            double miles = e.mlMilepost() - w.mlMilepost();
            int lanes = lanesFor("ML", w.mlMilepost(), e.mlMilepost());
            add(new Segment(w, e, "EB", miles, lanes));
            add(new Segment(e, w, "WB", miles, lanes));
        }
        for (int i = 0; i + 1 < northeast.size(); i++) {
            Interchange s = northeast.get(i), n = northeast.get(i + 1);
            double miles = n.neMilepost() - s.neMilepost();
            int lanes = lanesFor("NE", s.neMilepost(), n.neMilepost());
            add(new Segment(s, n, "NB", miles, lanes));
            add(new Segment(n, s, "SB", miles, lanes));
        }
    }

    private void add(Segment s) { segments.put(s.label(), s); }

    /** Segments driven along one road from a to b (both must be on that road). */
    private List<Segment> leg(List<Interchange> road, Interchange a, Interchange b) {
        List<Segment> out = new ArrayList<>();
        int i = road.indexOf(a), j = road.indexOf(b);
        int step = j > i ? 1 : -1;
        for (int k = i; k != j; k += step) {
            out.add(segments.get(road.get(k).id + ">" + road.get(k + step).id));
        }
        return out;
    }

    /** Full list of segments from entry to exit, in driving order. */
    public List<Segment> route(Interchange a, Interchange b) {
        if (a.isOnMainline() && b.isOnMainline()) return leg(mainline, a, b);
        if (a.isOnNortheast() && b.isOnNortheast()) return leg(northeast, a, b);
        List<Segment> out = new ArrayList<>(leg(a.isOnMainline() ? mainline : northeast, a, junction));
        out.addAll(leg(b.isOnMainline() ? mainline : northeast, junction, b));
        return out;
    }

    public double tripMiles(Interchange a, Interchange b) {
        double m = 0;
        for (Segment s : route(a, b)) m += s.miles;
        return m;
    }
}
