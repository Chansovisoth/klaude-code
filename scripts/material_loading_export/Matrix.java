/* Maintenance-only affine adapter for MaterialShapes on a JVM without Android.
 * Android pre/post translate order is retained; no geometry is approximated.
 */
package android.graphics;
public class Matrix {
  private float a = 1, b = 0, c = 0, d = 1, tx = 0, ty = 0;
  public void setScale(float x, float y) { a = x; d = y; b = c = tx = ty = 0; }
  public void setRotate(float degrees) {
    double radians = Math.toRadians(degrees);
    a = d = (float)Math.cos(radians); c = (float)Math.sin(radians); b = -c; tx = ty = 0;
  }
  public void setSkew(float x, float y) { a = d = 1; b = x; c = y; tx = ty = 0; }
  public boolean preTranslate(float x, float y) { tx += a*x + b*y; ty += c*x + d*y; return true; }
  public boolean postTranslate(float x, float y) { tx += x; ty += y; return true; }
  public void mapPoints(float[] points) {
    for (int i = 0; i < points.length; i += 2) {
      float x = points[i], y = points[i+1];
      points[i] = a*x + b*y + tx; points[i+1] = c*x + d*y + ty;
    }
  }
}
