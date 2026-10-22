package turnpike;

import java.util.ArrayList;
import java.util.List;

/**
 * The toll plazas used by the simulation, west to east, with approximate
 * mainline mileposts so they can be placed on the map. Mileposts are for
 * teaching only and are not official PA Turnpike Commission data.
 */
public final class TurnpikeData {

    /** One plaza's static facts. */
    public record PlazaInfo(String name, double milepost, String region) {
    }

    public static final List<PlazaInfo> PLAZAS = List.of(
            new PlazaInfo("Gateway (Ohio border)", 2, "Western PA"),
            new PlazaInfo("Warrendale", 30, "Western PA"),
            new PlazaInfo("Pittsburgh / Monroeville", 57, "Western PA"),
            new PlazaInfo("New Stanton", 75, "Western PA"),
            new PlazaInfo("Somerset", 110, "Laurel Highlands"),
            new PlazaInfo("Bedford", 146, "South Central PA"),
            new PlazaInfo("Breezewood", 161, "South Central PA"),
            new PlazaInfo("Harrisburg East", 247, "Central PA"),
            new PlazaInfo("Valley Forge", 326, "Eastern PA"),
            new PlazaInfo("Neshaminy Falls", 351, "Eastern PA"));

    /** Total length of the mainline drawn on the map, in miles. */
    public static final double MAINLINE_MILES = 360;

    private TurnpikeData() {
    }

    /** Fresh plaza objects (new queues and counters) for a new simulation run. */
    public static List<TollPlaza> createPlazas() {
        List<TollPlaza> out = new ArrayList<>();
        for (PlazaInfo p : PLAZAS) {
            out.add(new TollPlaza(p.name(), p.milepost()));
        }
        return out;
    }

    public static String regionOf(String plazaName) {
        for (PlazaInfo p : PLAZAS) {
            if (p.name().equals(plazaName)) {
                return p.region();
            }
        }
        return "";
    }
}
