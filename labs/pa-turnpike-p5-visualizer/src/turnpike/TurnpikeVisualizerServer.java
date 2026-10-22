package turnpike;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.awt.Desktop;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.Executors;

/**
 * Main class for the visualizer. Starts a small web server (built into the
 * JDK, so no libraries are needed) that serves the p5.js page and a JSON API
 * over the running simulation, then opens the page in your browser.
 *
 * <pre>
 *   GET  /                 p5.js page (resources/web/index.html)
 *   GET  /api/state        live snapshot: plazas, queues, moving cars, LIFO stack
 *   POST /api/run?cars=100&rush=true  start a run (rush=false keeps the original arrival timing)
 *   POST /api/stop         stop and freeze
 *   POST /api/reset        back to the static view
 * </pre>
 *
 * Run from Eclipse: right-click this file, then Run As, then Java Application.
 * Optional program argument: port (default 8213).
 */
public class TurnpikeVisualizerServer {

    private static final Map<String, String> TYPES = Map.of(
            "html", "text/html; charset=utf-8",
            "js", "application/javascript; charset=utf-8",
            "css", "text/css; charset=utf-8",
            "json", "application/json; charset=utf-8",
            "png", "image/png",
            "svg", "image/svg+xml");

    private final SimulationEngine engine = new SimulationEngine();

    public static void main(String[] args) throws IOException {
        int port = args.length > 0 ? Integer.parseInt(args[0]) : 8213;
        boolean openBrowser = !"--no-browser".equals(args.length > 1 ? args[1] : "");
        new TurnpikeVisualizerServer().start(port, openBrowser);
    }

    public void start(int port, boolean openBrowser) throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 0);
        server.createContext("/api/state", ex -> {
            if (allow(ex, "GET")) {
                send(ex, 200, TYPES.get("json"), engine.snapshotJson());
            }
        });
        server.createContext("/api/run", ex -> {
            if (allow(ex, "POST")) {
                String q = ex.getRequestURI().getQuery();
                engine.start(parseCars(q), q != null && q.contains("rush=true"));
                send(ex, 200, TYPES.get("json"), engine.snapshotJson());
            }
        });
        server.createContext("/api/stop", ex -> {
            if (allow(ex, "POST")) {
                engine.stop();
                send(ex, 200, TYPES.get("json"), engine.snapshotJson());
            }
        });
        server.createContext("/api/reset", ex -> {
            if (allow(ex, "POST")) {
                engine.reset();
                send(ex, 200, TYPES.get("json"), engine.snapshotJson());
            }
        });
        server.createContext("/", this::serveStatic);
        server.setExecutor(Executors.newFixedThreadPool(4));
        server.start();

        String url = "http://localhost:" + port + "/";
        System.out.println("==============================================================");
        System.out.println(" Pennsylvania Turnpike Visualizer running at " + url);
        System.out.println(" Open that address in a browser if it does not open by itself.");
        System.out.println(" Stop the server with the red square in Eclipse's Console view.");
        System.out.println("==============================================================");
        if (openBrowser) {
            openInBrowser(url);
        }
    }

    static int parseCars(String query) {
        int cars = 52;                           // same total as the console simulation
        if (query != null) {
            for (String kv : query.split("&")) {
                if (kv.startsWith("cars=")) {
                    try {
                        cars = Integer.parseInt(kv.substring(5));
                    } catch (NumberFormatException ignored) {
                        // keep default
                    }
                }
            }
        }
        return Math.max(3, Math.min(cars, 500));
    }

    private void serveStatic(HttpExchange ex) throws IOException {
        if (!allow(ex, "GET")) {
            return;
        }
        String path = ex.getRequestURI().getPath();
        if (path.equals("/")) {
            path = "/index.html";
        }
        if (path.contains("..")) {
            send(ex, 400, "text/plain", "bad path");
            return;
        }
        try (InputStream in = TurnpikeVisualizerServer.class.getResourceAsStream("/web" + path)) {
            if (in == null) {
                send(ex, 404, "text/plain", "not found: " + path);
                return;
            }
            byte[] body = in.readAllBytes();
            String ext = path.substring(path.lastIndexOf('.') + 1);
            ex.getResponseHeaders().set("Content-Type", TYPES.getOrDefault(ext, "application/octet-stream"));
            ex.sendResponseHeaders(200, body.length);
            try (OutputStream out = ex.getResponseBody()) {
                out.write(body);
            }
        }
    }

    private static boolean allow(HttpExchange ex, String method) throws IOException {
        if (!ex.getRequestMethod().equalsIgnoreCase(method)) {
            send(ex, 405, "text/plain", "use " + method);
            return false;
        }
        return true;
    }

    private static void send(HttpExchange ex, int status, String type, String text) throws IOException {
        byte[] body = text.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type", type);
        ex.getResponseHeaders().set("Cache-Control", "no-store");
        ex.sendResponseHeaders(status, body.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(body);
        }
    }

    private static void openInBrowser(String url) {
        try {
            if (Desktop.isDesktopSupported() && Desktop.getDesktop().isSupported(Desktop.Action.BROWSE)) {
                Desktop.getDesktop().browse(new URI(url));
            }
        } catch (Exception | Error e) {
            // Headless or no browser registered: the console message tells the user where to go.
        }
    }
}
