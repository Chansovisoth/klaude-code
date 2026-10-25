/* Copyright 2026 Klaude contributors. Apache-2.0.
 * Maintenance-only adapter: the upstream MaterialShapes and AndroidX Morph
 * perform all geometry construction and curve matching, without modification.
 */
import androidx.graphics.shapes.Cubic;
import androidx.graphics.shapes.Morph;
import androidx.graphics.shapes.RoundedPolygon;
import androidx.graphics.shapes.ShapesKt;
import androidx.graphics.shapes.Shapes_androidKt;
import androidx.graphics.shapes.CornerRounding;
import android.graphics.Matrix;
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
    if (args.length > 0 && args[0].equals("lock-shapes")) {
      String[] names = {"clover-4", "arrow", "clam-shell", "pentagon", "clock-cookie"};
      Matrix turn = new Matrix(); turn.setRotate(30);
      RoundedPolygon cookie = Shapes_androidKt.transformed(ShapesKt.star(
        RoundedPolygon.Companion, 14, 1f, .8f, new CornerRounding(1.5f / 14, 0)), turn);
      RoundedPolygon[] all = {MaterialShapes.CLOVER_4, MaterialShapes.ARROW,
        MaterialShapes.CLAM_SHELL, MaterialShapes.PENTAGON, cookie};
      System.out.print("{");
      for (int i = 0; i < all.length; i++) {
        if (i > 0) System.out.print(",");
        System.out.print("\"" + names[i] + "\":");
        path(MaterialShapes.normalize(all[i], true, new RectF(-1,-1,1,1)).getCubics());
      }
      System.out.println("}"); return;
    }
    if (args.length > 0 && args[0].equals("shapes")) {
      String[] names = {"circle", "pill", "oval", "diamond", "cookie", "burst", "sunny", "flower", "soft-burst"};
      RoundedPolygon[] all = {MaterialShapes.CIRCLE, MaterialShapes.PILL, MaterialShapes.OVAL,
        MaterialShapes.DIAMOND, MaterialShapes.COOKIE_9, MaterialShapes.BURST, MaterialShapes.SUNNY,
        MaterialShapes.FLOWER, MaterialShapes.SOFT_BURST};
      System.out.print("{");
      for (int i = 0; i < all.length; i++) {
        if (i > 0) System.out.print(",");
        System.out.print("\"" + names[i] + "\":");
        path(MaterialShapes.normalize(all[i], true, new RectF(-1,-1,1,1)).getCubics());
      }
      System.out.println("}");
      return;
    }
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
