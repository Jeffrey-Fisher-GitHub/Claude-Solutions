package turnpike;

/**
 * One toll interchange on the PA Turnpike, loaded from data/interchanges_2023.csv.
 *
 * Immutable: every field is final, so it can be shared by many threads with no locking.
 */
public final class Interchange {
    /** ML = Mainline (I-76/I-276), NE = Northeast Extension (I-476), JCT = Mid-County junction (on both). */
    public final String road;
    public final String id;
    public final String name;
    public final double milepost;
    public final int entryAADT;
    public final int exitAADT;
    public final int pctTrucks;

    public Interchange(String road, String id, String name, double milepost,
                       int entryAADT, int exitAADT, int pctTrucks) {
        this.road = road;
        this.id = id;
        this.name = name;
        this.milepost = milepost;
        this.entryAADT = entryAADT;
        this.exitAADT = exitAADT;
        this.pctTrucks = pctTrucks;
    }

    public boolean isOnMainline()  { return road.equals("ML") || road.equals("JCT"); }
    public boolean isOnNortheast() { return road.equals("NE") || road.equals("JCT"); }

    /** Milepost measured along the Northeast Extension (only meaningful when isOnNortheast()). */
    public double neMilepost() { return road.equals("JCT") ? 20.0 : milepost; }

    /** Milepost measured along the mainline (only meaningful when isOnMainline()). */
    public double mlMilepost() { return milepost; }

    @Override
    public String toString() { return id + " " + name; }
}
