/* Copyright 2026 Klaude contributors. Apache-2.0.
 * Maintenance-only adapter: the upstream MaterialShapes and AndroidX Morph
 * perform all geometry construction and curve matching, without modification.
 */
import androidx.graphics.shapes.Cubic;
import androidx.graphics.shapes.Morph;
import androidx.graphics.shapes.RoundedPolygon;
import android.graphics.RectF;
import com.google.android.material.shape.MaterialShapes;
import java.util.List;

public class Export {
  private static void path(List<Cubic> cubics) {
    System.out.print("[" + cubics.get(0).getAnchor0X() + "," + cubics.get(0).getAnchor0Y());
    for (Cubic c : cubics) {
      System.out.print("," + c.getControl0X() + "," + c.getControl0Y()
          + "," + c.getControl1X() + "," + c.getControl1Y()
          + "," + c.getAnchor1X() + "," + c.getAnchor1Y());
    }
    System.out.print("]");
  }
  public static void main(String[] args) {
    RoundedPolygon[] shapes = {
      MaterialShapes.SOFT_BURST, MaterialShapes.COOKIE_9, MaterialShapes.PENTAGON,
      MaterialShapes.PILL, MaterialShapes.SUNNY, MaterialShapes.COOKIE_4, MaterialShapes.OVAL
    };
    for (int i = 0; i < shapes.length; i++) {
      shapes[i] = MaterialShapes.normalize(shapes[i], true, new RectF(-1, -1, 1, 1));
    }
    System.out.print("[");
    for (int i = 0; i < shapes.length; i++) {
      if (i > 0) System.out.print(",");
      Morph morph = new Morph(shapes[i], shapes[(i + 1) % shapes.length]);
      System.out.print("{\"start\":"); path(morph.asCubics(0));
      System.out.print(",\"end\":"); path(morph.asCubics(1));
      System.out.print("}");
    }
    System.out.println("]");
  }
}
