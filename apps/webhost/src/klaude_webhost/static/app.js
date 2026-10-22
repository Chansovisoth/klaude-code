"use strict";

/* BEGIN BUNDLED MATERIAL LOADING: python3 scripts/bundle_webui_loading.py */
/* BEGIN EARLY MATERIAL COLORS: python3 scripts/bundle_webui_loading.py */
(()=>{/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function G(r){return r<0?-1:r===0?0:1}function st(r,t,e){return(1-e)*r+e*t}function me(r,t,e){return e<r?r:e>t?t:e}function U(r,t,e){return e<r?r:e>t?t:e}function lt(r){return r=r%360,r<0&&(r=r+360),r}function z(r){return r=r%360,r<0&&(r=r+360),r}function Wt(r,t){return 180-Math.abs(Math.abs(r-t)-180)}function yt(r,t){let e=r[0]*t[0][0]+r[1]*t[0][1]+r[2]*t[0][2],n=r[0]*t[1][0]+r[1]*t[1][1]+r[2]*t[1][2],a=r[0]*t[2][0]+r[1]*t[2][1]+r[2]*t[2][2];return[e,n,a]}/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var fe=[[.41233895,.35762064,.18051042],[.2126,.7152,.0722],[.01932141,.11916382,.95034478]],be=[[3.2413774792388685,-1.5376652402851851,-.49885366846268053],[-.9691452513005321,1.8758853451067872,.04156585616912061],[.05562093689691305,-.20395524564742123,1.0571799111220335]],Jt=[95.047,100,108.883];function ht(r,t,e){return(255<<24|(r&255)<<16|(t&255)<<8|e&255)>>>0}function Zt(r){let t=ct(r[0]),e=ct(r[1]),n=ct(r[2]);return ht(t,e,n)}function pe(r){return r>>24&255}function mt(r){return r>>16&255}function ft(r){return r>>8&255}function pt(r){return r&255}function Qt(r,t,e){let n=be,a=n[0][0]*r+n[0][1]*t+n[0][2]*e,o=n[1][0]*r+n[1][1]*t+n[1][2]*e,i=n[2][0]*r+n[2][1]*t+n[2][2]*e,c=ct(a),f=ct(o),g=ct(i);return ht(c,f,g)}function Fe(r){let t=et(mt(r)),e=et(ft(r)),n=et(pt(r));return yt([t,e,n],fe)}function de(r,t,e){let n=Jt,a=(r+16)/116,o=t/500+a,i=a-e/200,c=bt(o),f=bt(a),g=bt(i),m=c*n[0],y=f*n[1],P=g*n[2];return Qt(m,y,P)}function Ft(r){let t=et(mt(r)),e=et(ft(r)),n=et(pt(r)),a=fe,o=a[0][0]*t+a[0][1]*e+a[0][2]*n,i=a[1][0]*t+a[1][1]*e+a[1][2]*n,c=a[2][0]*t+a[2][1]*e+a[2][2]*n,f=Jt,g=o/f[0],m=i/f[1],y=c/f[2],P=Pt(g),d=Pt(m),p=Pt(y),l=116*d-16,C=500*(P-d),v=200*(d-p);return[l,C,v]}function ge(r){let t=j(r),e=ct(t);return ht(e,e,e)}function wt(r){let t=Fe(r)[1];return 116*Pt(t/100)-16}function j(r){return 100*bt((r+16)/116)}function Ct(r){return Pt(r/100)*116-16}function et(r){let t=r/255;return t<=.040449936?t/12.92*100:Math.pow((t+.055)/1.055,2.4)*100}function ct(r){let t=r/100,e=0;return t<=.0031308?e=t*12.92:e=1.055*Math.pow(t,1/2.4)-.055,me(0,255,Math.round(e*255))}function ye(){return Jt}function Pt(r){let t=.008856451679035631,e=24389/27;return r>t?Math.pow(r,1/3):(e*r+16)/116}function bt(r){let t=.008856451679035631,e=24389/27,n=r*r*r;return n>t?n:(116*r-16)/e}/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var X=class r{static make(t=ye(),e=200/Math.PI*j(50)/100,n=50,a=2,o=!1){let i=t,c=i[0]*.401288+i[1]*.650173+i[2]*-.051461,f=i[0]*-.250268+i[1]*1.204414+i[2]*.045854,g=i[0]*-.002079+i[1]*.048952+i[2]*.953127,m=.8+a/10,y=m>=.9?st(.59,.69,(m-.9)*10):st(.525,.59,(m-.8)*10),P=o?1:m*(1-1/3.6*Math.exp((-e-42)/92));P=P>1?1:P<0?0:P;let d=m,p=[P*(100/c)+1-P,P*(100/f)+1-P,P*(100/g)+1-P],l=1/(5*e+1),C=l*l*l*l,v=1-C,S=C*e+.1*v*v*Math.cbrt(5*e),k=j(n)/t[1],I=1.48+Math.sqrt(k),L=.725/Math.pow(k,.2),O=L,A=[Math.pow(S*p[0]*c/100,.42),Math.pow(S*p[1]*f/100,.42),Math.pow(S*p[2]*g/100,.42)],E=[400*A[0]/(A[0]+27.13),400*A[1]/(A[1]+27.13),400*A[2]/(A[2]+27.13)],V=(2*E[0]+E[1]+.05*E[2])*L;return new r(k,V,L,O,y,d,p,S,Math.pow(S,.25),I)}constructor(t,e,n,a,o,i,c,f,g,m){this.n=t,this.aw=e,this.nbb=n,this.ncb=a,this.c=o,this.nc=i,this.rgbD=c,this.fl=f,this.fLRoot=g,this.z=m}};X.DEFAULT=X.make();/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var rt=class r{constructor(t,e,n,a,o,i,c,f,g){this.hue=t,this.chroma=e,this.j=n,this.q=a,this.m=o,this.s=i,this.jstar=c,this.astar=f,this.bstar=g}distance(t){let e=this.jstar-t.jstar,n=this.astar-t.astar,a=this.bstar-t.bstar,o=Math.sqrt(e*e+n*n+a*a);return 1.41*Math.pow(o,.63)}static fromInt(t){return r.fromIntInViewingConditions(t,X.DEFAULT)}static fromIntInViewingConditions(t,e){let n=(t&16711680)>>16,a=(t&65280)>>8,o=t&255,i=et(n),c=et(a),f=et(o),g=.41233895*i+.35762064*c+.18051042*f,m=.2126*i+.7152*c+.0722*f,y=.01932141*i+.11916382*c+.95034478*f,P=.401288*g+.650173*m-.051461*y,d=-.250268*g+1.204414*m+.045854*y,p=-.002079*g+.048952*m+.953127*y,l=e.rgbD[0]*P,C=e.rgbD[1]*d,v=e.rgbD[2]*p,S=Math.pow(e.fl*Math.abs(l)/100,.42),k=Math.pow(e.fl*Math.abs(C)/100,.42),I=Math.pow(e.fl*Math.abs(v)/100,.42),L=G(l)*400*S/(S+27.13),O=G(C)*400*k/(k+27.13),A=G(v)*400*I/(I+27.13),E=(11*L+-12*O+A)/11,V=(L+O-2*A)/9,R=(20*L+20*O+21*A)/20,Y=(40*L+20*O+A)/20,tt=Math.atan2(V,E)*180/Math.PI,_=z(tt),it=_*Math.PI/180,Tt=Y*e.nbb,at=100*Math.pow(Tt/e.aw,e.c*e.z),Dt=4/e.c*Math.sqrt(at/100)*(e.aw+4)*e.fLRoot,Xt=_<20.14?_+360:_,qt=.25*(Math.cos(Xt*Math.PI/180+2)+3.8),jt=5e4/13*qt*e.nc*e.ncb*Math.sqrt(E*E+V*V)/(R+.305),kt=Math.pow(jt,.9)*Math.pow(1.64-Math.pow(.29,e.n),.73),ue=kt*Math.sqrt(at/100),le=ue*e.fLRoot,Ae=50*Math.sqrt(kt*e.c/(e.aw+4)),Te=(1+100*.007)*at/(1+.007*at),he=1/.0228*Math.log(1+.0228*le),De=he*Math.cos(it),ke=he*Math.sin(it);return new r(_,ue,at,Dt,le,Ae,Te,De,ke)}static fromJch(t,e,n){return r.fromJchInViewingConditions(t,e,n,X.DEFAULT)}static fromJchInViewingConditions(t,e,n,a){let o=4/a.c*Math.sqrt(t/100)*(a.aw+4)*a.fLRoot,i=e*a.fLRoot,c=e/Math.sqrt(t/100),f=50*Math.sqrt(c*a.c/(a.aw+4)),g=n*Math.PI/180,m=(1+100*.007)*t/(1+.007*t),y=1/.0228*Math.log(1+.0228*i),P=y*Math.cos(g),d=y*Math.sin(g);return new r(n,e,t,o,i,f,m,P,d)}static fromUcs(t,e,n){return r.fromUcsInViewingConditions(t,e,n,X.DEFAULT)}static fromUcsInViewingConditions(t,e,n,a){let o=e,i=n,c=Math.sqrt(o*o+i*i),g=(Math.exp(c*.0228)-1)/.0228/a.fLRoot,m=Math.atan2(i,o)*(180/Math.PI);m<0&&(m+=360);let y=t/(1-(t-100)*.007);return r.fromJchInViewingConditions(y,g,m,a)}toInt(){return this.viewed(X.DEFAULT)}viewed(t){let e=this.chroma===0||this.j===0?0:this.chroma/Math.sqrt(this.j/100),n=Math.pow(e/Math.pow(1.64-Math.pow(.29,t.n),.73),1/.9),a=this.hue*Math.PI/180,o=.25*(Math.cos(a+2)+3.8),i=t.aw*Math.pow(this.j/100,1/t.c/t.z),c=o*(5e4/13)*t.nc*t.ncb,f=i/t.nbb,g=Math.sin(a),m=Math.cos(a),y=23*(f+.305)*n/(23*c+11*n*m+108*n*g),P=y*m,d=y*g,p=(460*f+451*P+288*d)/1403,l=(460*f-891*P-261*d)/1403,C=(460*f-220*P-6300*d)/1403,v=Math.max(0,27.13*Math.abs(p)/(400-Math.abs(p))),S=G(p)*(100/t.fl)*Math.pow(v,1/.42),k=Math.max(0,27.13*Math.abs(l)/(400-Math.abs(l))),I=G(l)*(100/t.fl)*Math.pow(k,1/.42),L=Math.max(0,27.13*Math.abs(C)/(400-Math.abs(C))),O=G(C)*(100/t.fl)*Math.pow(L,1/.42),A=S/t.rgbD[0],E=I/t.rgbD[1],V=O/t.rgbD[2],R=1.86206786*A-1.01125463*E+.14918677*V,Y=.38752654*A+.62144744*E-.00897398*V,q=-.0158415*A-.03412294*E+1.04996444*V;return Qt(R,Y,q)}static fromXyzInViewingConditions(t,e,n,a){let o=.401288*t+.650173*e-.051461*n,i=-.250268*t+1.204414*e+.045854*n,c=-.002079*t+.048952*e+.953127*n,f=a.rgbD[0]*o,g=a.rgbD[1]*i,m=a.rgbD[2]*c,y=Math.pow(a.fl*Math.abs(f)/100,.42),P=Math.pow(a.fl*Math.abs(g)/100,.42),d=Math.pow(a.fl*Math.abs(m)/100,.42),p=G(f)*400*y/(y+27.13),l=G(g)*400*P/(P+27.13),C=G(m)*400*d/(d+27.13),v=(11*p+-12*l+C)/11,S=(p+l-2*C)/9,k=(20*p+20*l+21*C)/20,I=(40*p+20*l+C)/20,O=Math.atan2(S,v)*180/Math.PI,A=O<0?O+360:O>=360?O-360:O,E=A*Math.PI/180,V=I*a.nbb,R=100*Math.pow(V/a.aw,a.c*a.z),Y=4/a.c*Math.sqrt(R/100)*(a.aw+4)*a.fLRoot,q=A<20.14?A+360:A,tt=1/4*(Math.cos(q*Math.PI/180+2)+3.8),it=5e4/13*tt*a.nc*a.ncb*Math.sqrt(v*v+S*S)/(k+.305),Tt=Math.pow(it,.9)*Math.pow(1.64-Math.pow(.29,a.n),.73),at=Tt*Math.sqrt(R/100),Dt=at*a.fLRoot,Xt=50*Math.sqrt(Tt*a.c/(a.aw+4)),qt=(1+100*.007)*R/(1+.007*R),$t=Math.log(1+.0228*Dt)/.0228,jt=$t*Math.cos(E),kt=$t*Math.sin(E);return new r(A,at,R,Y,Dt,Xt,qt,jt,kt)}xyzInViewingConditions(t){let e=this.chroma===0||this.j===0?0:this.chroma/Math.sqrt(this.j/100),n=Math.pow(e/Math.pow(1.64-Math.pow(.29,t.n),.73),1/.9),a=this.hue*Math.PI/180,o=.25*(Math.cos(a+2)+3.8),i=t.aw*Math.pow(this.j/100,1/t.c/t.z),c=o*(5e4/13)*t.nc*t.ncb,f=i/t.nbb,g=Math.sin(a),m=Math.cos(a),y=23*(f+.305)*n/(23*c+11*n*m+108*n*g),P=y*m,d=y*g,p=(460*f+451*P+288*d)/1403,l=(460*f-891*P-261*d)/1403,C=(460*f-220*P-6300*d)/1403,v=Math.max(0,27.13*Math.abs(p)/(400-Math.abs(p))),S=G(p)*(100/t.fl)*Math.pow(v,1/.42),k=Math.max(0,27.13*Math.abs(l)/(400-Math.abs(l))),I=G(l)*(100/t.fl)*Math.pow(k,1/.42),L=Math.max(0,27.13*Math.abs(C)/(400-Math.abs(C))),O=G(C)*(100/t.fl)*Math.pow(L,1/.42),A=S/t.rgbD[0],E=I/t.rgbD[1],V=O/t.rgbD[2],R=1.86206786*A-1.01125463*E+.14918677*V,Y=.38752654*A+.62144744*E-.00897398*V,q=-.0158415*A-.03412294*E+1.04996444*V;return[R,Y,q]}};/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var J=class r{static sanitizeRadians(t){return(t+Math.PI*8)%(Math.PI*2)}static trueDelinearized(t){let e=t/100,n=0;return e<=.0031308?n=e*12.92:n=1.055*Math.pow(e,1/2.4)-.055,n*255}static chromaticAdaptation(t){let e=Math.pow(Math.abs(t),.42);return G(t)*400*e/(e+27.13)}static hueOf(t){let e=yt(t,r.SCALED_DISCOUNT_FROM_LINRGB),n=r.chromaticAdaptation(e[0]),a=r.chromaticAdaptation(e[1]),o=r.chromaticAdaptation(e[2]),i=(11*n+-12*a+o)/11,c=(n+a-2*o)/9;return Math.atan2(c,i)}static areInCyclicOrder(t,e,n){let a=r.sanitizeRadians(e-t),o=r.sanitizeRadians(n-t);return a<o}static intercept(t,e,n){return(e-t)/(n-t)}static lerpPoint(t,e,n){return[t[0]+(n[0]-t[0])*e,t[1]+(n[1]-t[1])*e,t[2]+(n[2]-t[2])*e]}static setCoordinate(t,e,n,a){let o=r.intercept(t[a],e,n[a]);return r.lerpPoint(t,o,n)}static isBounded(t){return 0<=t&&t<=100}static nthVertex(t,e){let n=r.Y_FROM_LINRGB[0],a=r.Y_FROM_LINRGB[1],o=r.Y_FROM_LINRGB[2],i=e%4<=1?0:100,c=e%2===0?0:100;if(e<4){let f=i,g=c,m=(t-f*a-g*o)/n;return r.isBounded(m)?[m,f,g]:[-1,-1,-1]}else if(e<8){let f=i,g=c,m=(t-g*n-f*o)/a;return r.isBounded(m)?[g,m,f]:[-1,-1,-1]}else{let f=i,g=c,m=(t-f*n-g*a)/o;return r.isBounded(m)?[f,g,m]:[-1,-1,-1]}}static bisectToSegment(t,e){let n=[-1,-1,-1],a=n,o=0,i=0,c=!1,f=!0;for(let g=0;g<12;g++){let m=r.nthVertex(t,g);if(m[0]<0)continue;let y=r.hueOf(m);if(!c){n=m,a=m,o=y,i=y,c=!0;continue}(f||r.areInCyclicOrder(o,y,i))&&(f=!1,r.areInCyclicOrder(o,e,y)?(a=m,i=y):(n=m,o=y))}return[n,a]}static midpoint(t,e){return[(t[0]+e[0])/2,(t[1]+e[1])/2,(t[2]+e[2])/2]}static criticalPlaneBelow(t){return Math.floor(t-.5)}static criticalPlaneAbove(t){return Math.ceil(t-.5)}static bisectToLimit(t,e){let n=r.bisectToSegment(t,e),a=n[0],o=r.hueOf(a),i=n[1];for(let c=0;c<3;c++)if(a[c]!==i[c]){let f=-1,g=255;a[c]<i[c]?(f=r.criticalPlaneBelow(r.trueDelinearized(a[c])),g=r.criticalPlaneAbove(r.trueDelinearized(i[c]))):(f=r.criticalPlaneAbove(r.trueDelinearized(a[c])),g=r.criticalPlaneBelow(r.trueDelinearized(i[c])));for(let m=0;m<8&&!(Math.abs(g-f)<=1);m++){let y=Math.floor((f+g)/2),P=r.CRITICAL_PLANES[y],d=r.setCoordinate(a,P,i,c),p=r.hueOf(d);r.areInCyclicOrder(o,e,p)?(i=d,g=y):(a=d,o=p,f=y)}}return r.midpoint(a,i)}static inverseChromaticAdaptation(t){let e=Math.abs(t),n=Math.max(0,27.13*e/(400-e));return G(t)*Math.pow(n,1/.42)}static findResultByJ(t,e,n){let a=Math.sqrt(n)*11,o=X.DEFAULT,i=1/Math.pow(1.64-Math.pow(.29,o.n),.73),f=.25*(Math.cos(t+2)+3.8)*(5e4/13)*o.nc*o.ncb,g=Math.sin(t),m=Math.cos(t);for(let y=0;y<5;y++){let P=a/100,d=e===0||a===0?0:e/Math.sqrt(P),p=Math.pow(d*i,1/.9),C=o.aw*Math.pow(P,1/o.c/o.z)/o.nbb,v=23*(C+.305)*p/(23*f+11*p*m+108*p*g),S=v*m,k=v*g,I=(460*C+451*S+288*k)/1403,L=(460*C-891*S-261*k)/1403,O=(460*C-220*S-6300*k)/1403,A=r.inverseChromaticAdaptation(I),E=r.inverseChromaticAdaptation(L),V=r.inverseChromaticAdaptation(O),R=yt([A,E,V],r.LINRGB_FROM_SCALED_DISCOUNT);if(R[0]<0||R[1]<0||R[2]<0)return 0;let Y=r.Y_FROM_LINRGB[0],q=r.Y_FROM_LINRGB[1],tt=r.Y_FROM_LINRGB[2],_=Y*R[0]+q*R[1]+tt*R[2];if(_<=0)return 0;if(y===4||Math.abs(_-n)<.002)return R[0]>100.01||R[1]>100.01||R[2]>100.01?0:Zt(R);a=a-(_-n)*a/(2*_)}return 0}static solveToInt(t,e,n){if(e<1e-4||n<1e-4||n>99.9999)return ge(n);t=z(t);let a=t/180*Math.PI,o=j(n),i=r.findResultByJ(a,e,o);if(i!==0)return i;let c=r.bisectToLimit(o,a);return Zt(c)}static solveToCam(t,e,n){return rt.fromInt(r.solveToInt(t,e,n))}};J.SCALED_DISCOUNT_FROM_LINRGB=[[.001200833568784504,.002389694492170889,.0002795742885861124],[.0005891086651375999,.0029785502573438758,.0003270666104008398],[.00010146692491640572,.0005364214359186694,.0032979401770712076]];J.LINRGB_FROM_SCALED_DISCOUNT=[[1373.2198709594231,-1100.4251190754821,-7.278681089101213],[-271.815969077903,559.6580465940733,-32.46047482791194],[1.9622899599665666,-57.173814538844006,308.7233197812385]];J.Y_FROM_LINRGB=[.2126,.7152,.0722];J.CRITICAL_PLANES=[.015176349177441876,.045529047532325624,.07588174588720938,.10623444424209313,.13658714259697685,.16693984095186062,.19729253930674434,.2276452376616281,.2579979360165119,.28835063437139563,.3188300904430532,.350925934958123,.3848314933096426,.42057480301049466,.458183274052838,.4976837250274023,.5391024159806381,.5824650784040898,.6277969426914107,.6751227633498623,.7244668422128921,.775853049866786,.829304845476233,.8848452951698498,.942497089126609,1.0022825574869039,1.0642236851973577,1.1283421258858297,1.1946592148522128,1.2631959812511864,1.3339731595349034,1.407011200216447,1.4823302800086415,1.5599503113873272,1.6398909516233677,1.7221716113234105,1.8068114625156377,1.8938294463134073,1.9832442801866852,2.075074464868551,2.1693382909216234,2.2660538449872063,2.36523901573795,2.4669114995532007,2.5710888059345764,2.6777882626779785,2.7870270208169257,2.898822059350997,3.0131901897720907,3.1301480604002863,3.2497121605402226,3.3718988244681087,3.4967242352587946,3.624204428461639,3.754355295633311,3.887192587735158,4.022731918402185,4.160988767090289,4.301978482107941,4.445716283538092,4.592217266055746,4.741496401646282,4.893568542229298,5.048448422192488,5.20615066083972,5.3666897647573375,5.5300801301023865,5.696336044816294,5.865471690767354,6.037501145825082,6.212438385869475,6.390297286737924,6.571091626112461,6.7548350853498045,6.941541251256611,7.131223617812143,7.323895587840543,7.5195704746346665,7.7182615035334345,7.919981813454504,8.124744458384042,8.332562408825165,8.543448553206703,8.757415699253682,8.974476575321063,9.194643831691977,9.417930041841839,9.644347703669503,9.873909240696694,10.106627003236781,10.342513269534024,10.58158024687427,10.8238400726681,11.069304815507364,11.317986476196008,11.569896988756009,11.825048221409341,12.083451977536606,12.345119996613247,12.610063955123938,12.878295467455942,13.149826086772048,13.42466730586372,13.702830557985108,13.984327217668513,14.269168601521828,14.55736596900856,14.848930523210871,15.143873411576273,15.44220572664832,15.743938506781891,16.04908273684337,16.35764934889634,16.66964922287304,16.985093187232053,17.30399201960269,17.62635644741625,17.95219714852476,18.281524751807332,18.614349837764564,18.95068293910138,19.290534541298456,19.633915083172692,19.98083495742689,20.331304511189067,20.685334046541502,21.042933821039977,21.404114048223256,21.76888489811322,22.137256497705877,22.50923893145328,22.884842241736916,23.264076429332462,23.6469514538663,24.033477234264016,24.42366364919083,24.817520537484558,25.21505769858089,25.61628489293138,26.021211842414342,26.429848230738664,26.842203703840827,27.258287870275353,27.678110301598522,28.10168053274597,28.529008062403893,28.96010235337422,29.39497283293396,29.83362889318845,30.276079891419332,30.722335150426627,31.172403958865512,31.62629557157785,32.08401920991837,32.54558406207592,33.010999283389665,33.4802739966603,33.953417292456834,34.430438229418264,34.911345834551085,35.39614910352207,35.88485700094671,36.37747846067349,36.87402238606382,37.37449765026789,37.87891309649659,38.38727753828926,38.89959975977785,39.41588851594697,39.93615253289054,40.460400508064545,40.98864111053629,41.520882981230194,42.05713473317016,42.597404951718396,43.141702194811224,43.6900349931913,44.24241185063697,44.798841244188324,45.35933162437017,45.92389141541209,46.49252901546552,47.065252796817916,47.64207110610409,48.22299226451468,48.808024568002054,49.3971762874833,49.9904556690408,50.587870934119984,51.189430279724725,51.79514187861014,52.40501387947288,53.0190544071392,53.637271562750364,54.259673423945976,54.88626804504493,55.517063457223934,56.15206766869424,56.79128866487574,57.43473440856916,58.08241284012621,58.734331877617365,59.39049941699807,60.05092333227251,60.715611475655585,61.38457167773311,62.057811747619894,62.7353394731159,63.417162620860914,64.10328893648692,64.79372614476921,65.48848194977529,66.18756403501224,66.89098006357258,67.59873767827808,68.31084450182222,69.02730813691093,69.74813616640164,70.47333615344107,71.20291564160104,71.93688215501312,72.67524319850172,73.41800625771542,74.16517879925733,74.9167682708136,75.67278210128072,76.43322770089146,77.1981124613393,77.96744375590167,78.74122893956174,79.51947534912904,80.30219030335869,81.08938110306934,81.88105503125999,82.67721935322541,83.4778813166706,84.28304815182372,85.09272707154808,85.90692527145302,86.72564993000343,87.54890820862819,88.3767072518277,89.2090541872801,90.04595612594655,90.88742016217518,91.73345337380438,92.58406282226491,93.43925555268066,94.29903859396902,95.16341895893969,96.03240364439274,96.9059996312159,97.78421388448044,98.6670533535366,99.55452497210776];/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var T=class r{static from(t,e,n){return new r(J.solveToInt(t,e,n))}static fromInt(t){return new r(t)}toInt(){return this.argb}get hue(){return this.internalHue}set hue(t){this.setInternalState(J.solveToInt(t,this.internalChroma,this.internalTone))}get chroma(){return this.internalChroma}set chroma(t){this.setInternalState(J.solveToInt(this.internalHue,t,this.internalTone))}get tone(){return this.internalTone}set tone(t){this.setInternalState(J.solveToInt(this.internalHue,this.internalChroma,t))}setValue(t,e){this[t]=e}toString(){return`HCT(${this.hue.toFixed(0)}, ${this.chroma.toFixed(0)}, ${this.tone.toFixed(0)})`}static isBlue(t){return t>=250&&t<270}static isYellow(t){return t>=105&&t<125}static isCyan(t){return t>=170&&t<207}constructor(t){this.argb=t;let e=rt.fromInt(t);this.internalHue=e.hue,this.internalChroma=e.chroma,this.internalTone=wt(t),this.argb=t}setInternalState(t){let e=rt.fromInt(t);this.internalHue=e.hue,this.internalChroma=e.chroma,this.internalTone=wt(t),this.argb=t}inViewingConditions(t){let n=rt.fromInt(this.toInt()).xyzInViewingConditions(t),a=rt.fromXyzInViewingConditions(n[0],n[1],n[2],X.make());return r.from(a.hue,a.chroma,Ct(n[1]))}};/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *//**
 * @license
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var H=class r{static ratioOfTones(t,e){return t=U(0,100,t),e=U(0,100,e),r.ratioOfYs(j(t),j(e))}static ratioOfYs(t,e){let n=t>e?t:e,a=n===e?t:e;return(n+5)/(a+5)}static lighter(t,e){if(t<0||t>100)return-1;let n=j(t),a=e*(n+5)-5,o=r.ratioOfYs(a,n),i=Math.abs(o-e);if(o<e&&i>.04)return-1;let c=Ct(a)+.4;return c<0||c>100?-1:c}static darker(t,e){if(t<0||t>100)return-1;let n=j(t),a=(n+5)/e-5,o=r.ratioOfYs(n,a),i=Math.abs(o-e);if(o<e&&i>.04)return-1;let c=Ct(a)-.4;return c<0||c>100?-1:c}static lighterUnsafe(t,e){let n=r.lighter(t,e);return n<0?100:n}static darkerUnsafe(t,e){let n=r.darker(t,e);return n<0?0:n}};/**
 * @license
 * Copyright 2023 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var ut=class r{static isDisliked(t){let e=Math.round(t.hue)>=90&&Math.round(t.hue)<=111,n=Math.round(t.chroma)>16,a=Math.round(t.tone)<65;return e&&n&&a}static fixIfDisliked(t){return r.isDisliked(t)?T.from(t.hue,t.chroma,70):t}};/**
 * @license
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function we(r,t,e){if(r.name!==e.name)throw new Error(`Attempting to extend color ${r.name} with color ${e.name} of different name for spec version ${t}.`);if(r.isBackground!==e.isBackground)throw new Error(`Attempting to extend color ${r.name} as a ${r.isBackground?"background":"foreground"} with color ${e.name} as a ${e.isBackground?"background":"foreground"} for spec version ${t}.`)}function w(r,t,e){return we(r,t,e),u.fromPalette({name:r.name,palette:n=>n.specVersion===t?e.palette(n):r.palette(n),tone:n=>n.specVersion===t?e.tone(n):r.tone(n),isBackground:r.isBackground,chromaMultiplier:n=>{let a=n.specVersion===t?e.chromaMultiplier:r.chromaMultiplier;return a!==void 0?a(n):1},background:n=>{let a=n.specVersion===t?e.background:r.background;return a!==void 0?a(n):void 0},secondBackground:n=>{let a=n.specVersion===t?e.secondBackground:r.secondBackground;return a!==void 0?a(n):void 0},contrastCurve:n=>{let a=n.specVersion===t?e.contrastCurve:r.contrastCurve;return a!==void 0?a(n):void 0},toneDeltaPair:n=>{let a=n.specVersion===t?e.toneDeltaPair:r.toneDeltaPair;return a!==void 0?a(n):void 0}})}var u=class r{static fromPalette(t){return new r(t.name??"",t.palette,t.tone??r.getInitialToneFromBackground(t.background),t.isBackground??!1,t.chromaMultiplier,t.background,t.secondBackground,t.contrastCurve,t.toneDeltaPair)}static getInitialToneFromBackground(t){return t===void 0?e=>50:e=>t(e)?t(e).getTone(e):50}constructor(t,e,n,a,o,i,c,f,g){if(this.name=t,this.palette=e,this.tone=n,this.isBackground=a,this.chromaMultiplier=o,this.background=i,this.secondBackground=c,this.contrastCurve=f,this.toneDeltaPair=g,this.hctCache=new Map,!i&&c)throw new Error(`Color ${t} has secondBackgrounddefined, but background is not defined.`);if(!i&&f)throw new Error(`Color ${t} has contrastCurvedefined, but background is not defined.`);if(i&&!f)throw new Error(`Color ${t} has backgrounddefined, but contrastCurve is not defined.`)}clone(){return r.fromPalette({name:this.name,palette:this.palette,tone:this.tone,isBackground:this.isBackground,chromaMultiplier:this.chromaMultiplier,background:this.background,secondBackground:this.secondBackground,contrastCurve:this.contrastCurve,toneDeltaPair:this.toneDeltaPair})}clearCache(){this.hctCache.clear()}getArgb(t){return this.getHct(t).toInt()}getHct(t){let e=this.hctCache.get(t);if(e!=null)return e;let n=Pe(t.specVersion).getHct(t,this);return this.hctCache.size>4&&this.hctCache.clear(),this.hctCache.set(t,n),n}getTone(t){return Pe(t.specVersion).getTone(t,this)}static foregroundTone(t,e){let n=H.lighterUnsafe(t,e),a=H.darkerUnsafe(t,e),o=H.ratioOfTones(n,t),i=H.ratioOfTones(a,t);if(r.tonePrefersLightForeground(t)){let f=Math.abs(o-i)<.1&&o<e&&i<e;return o>=e||o>=i||f?n:a}else return i>=e||i>=o?a:n}static tonePrefersLightForeground(t){return Math.round(t)<60}static toneAllowsLightForeground(t){return Math.round(t)<=49}static enableLightForeground(t){return r.tonePrefersLightForeground(t)&&!r.toneAllowsLightForeground(t)?49:t}},te=class{getHct(t,e){let n=e.getTone(t);return e.palette(t).getHct(n)}getTone(t,e){let n=t.contrastLevel<0,a=e.toneDeltaPair?e.toneDeltaPair(t):void 0;if(a){let o=a.roleA,i=a.roleB,c=a.delta,f=a.polarity,g=a.stayTogether,m=f==="nearer"||f==="lighter"&&!t.isDark||f==="darker"&&t.isDark,y=m?o:i,P=m?i:o,d=e.name===y.name,p=t.isDark?1:-1,l=y.tone(t),C=P.tone(t);if(e.background&&y.contrastCurve&&P.contrastCurve){let v=e.background(t),S=y.contrastCurve(t),k=P.contrastCurve(t);if(v&&S&&k){let I=v.getTone(t),L=S.get(t.contrastLevel),O=k.get(t.contrastLevel);H.ratioOfTones(I,l)<L&&(l=u.foregroundTone(I,L)),H.ratioOfTones(I,C)<O&&(C=u.foregroundTone(I,O)),n&&(l=u.foregroundTone(I,L),C=u.foregroundTone(I,O))}}return(C-l)*p<c&&(C=U(0,100,l+c*p),(C-l)*p>=c||(l=U(0,100,C-c*p))),50<=l&&l<60?p>0?(l=60,C=Math.max(C,l+c*p)):(l=49,C=Math.min(C,l+c*p)):50<=C&&C<60&&(g?p>0?(l=60,C=Math.max(C,l+c*p)):(l=49,C=Math.min(C,l+c*p)):p>0?C=60:C=49),d?l:C}else{let o=e.tone(t);if(e.background==null||e.background(t)===void 0||e.contrastCurve==null||e.contrastCurve(t)===void 0)return o;let i=e.background(t).getTone(t),c=e.contrastCurve(t).get(t.contrastLevel);if(H.ratioOfTones(i,o)>=c||(o=u.foregroundTone(i,c)),n&&(o=u.foregroundTone(i,c)),e.isBackground&&50<=o&&o<60&&(H.ratioOfTones(49,i)>=c?o=49:o=60),e.secondBackground==null||e.secondBackground(t)===void 0)return o;let[f,g]=[e.background,e.secondBackground],[m,y]=[f(t).getTone(t),g(t).getTone(t)],[P,d]=[Math.max(m,y),Math.min(m,y)];if(H.ratioOfTones(P,o)>=c&&H.ratioOfTones(d,o)>=c)return o;let p=H.lighter(P,c),l=H.darker(d,c),C=[];return p!==-1&&C.push(p),l!==-1&&C.push(l),u.tonePrefersLightForeground(m)||u.tonePrefersLightForeground(y)?p<0?100:p:C.length===1?C[0]:l<0?0:l}}},ee=class{getHct(t,e){let n=e.palette(t),a=e.getTone(t),o=n.hue,i=n.chroma*(e.chromaMultiplier?e.chromaMultiplier(t):1);return T.from(o,i,a)}getTone(t,e){let n=e.toneDeltaPair?e.toneDeltaPair(t):void 0;if(n){let a=n.roleA,o=n.roleB,i=n.polarity,c=n.constraint,f=i==="darker"||i==="relative_lighter"&&t.isDark||i==="relative_darker"&&!t.isDark?-n.delta:n.delta,g=e.name===a.name,m=g?a:o,y=g?o:a,P=m.tone(t),d=y.getTone(t),p=f*(g?1:-1);if(c==="exact"?P=U(0,100,d+p):c==="nearer"?p>0?P=U(0,100,U(d,d+p,P)):P=U(0,100,U(d+p,d,P)):c==="farther"&&(p>0?P=U(d+p,100,P):P=U(0,d+p,P)),e.background&&e.contrastCurve){let l=e.background(t),C=e.contrastCurve(t);if(l&&C){let v=l.getTone(t),S=C.get(t.contrastLevel);P=H.ratioOfTones(v,P)>=S&&t.contrastLevel>=0?P:u.foregroundTone(v,S)}}return e.isBackground&&!e.name.endsWith("_fixed_dim")&&(P>=57?P=U(65,100,P):P=U(0,49,P)),P}else{let a=e.tone(t);if(e.background==null||e.background(t)===void 0||e.contrastCurve==null||e.contrastCurve(t)===void 0)return a;let o=e.background(t).getTone(t),i=e.contrastCurve(t).get(t.contrastLevel);if(a=H.ratioOfTones(o,a)>=i&&t.contrastLevel>=0?a:u.foregroundTone(o,i),e.isBackground&&!e.name.endsWith("_fixed_dim")&&(a>=57?a=U(65,100,a):a=U(0,49,a)),e.secondBackground==null||e.secondBackground(t)===void 0)return a;let[c,f]=[e.background,e.secondBackground],[g,m]=[c(t).getTone(t),f(t).getTone(t)],[y,P]=[Math.max(g,m),Math.min(g,m)];if(H.ratioOfTones(y,a)>=i&&H.ratioOfTones(P,a)>=i)return a;let d=H.lighter(y,i),p=H.darker(P,i),l=[];return d!==-1&&l.push(d),p!==-1&&l.push(p),u.tonePrefersLightForeground(g)||u.tonePrefersLightForeground(m)?d<0?100:d:l.length===1?l[0]:p<0?0:p}}},ve=new te,Ee=new ee;function Pe(r){return r==="2025"?Ee:ve}/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var x=class r{static fromInt(t){let e=T.fromInt(t);return r.fromHct(e)}static fromHct(t){return new r(t.hue,t.chroma,t)}static fromHueAndChroma(t,e){let n=new re(t,e).create();return new r(t,e,n)}constructor(t,e,n){this.hue=t,this.chroma=e,this.keyColor=n,this.cache=new Map}tone(t){let e=this.cache.get(t);return e===void 0&&(t==99&&T.isYellow(this.hue)?e=this.averageArgb(this.tone(98),this.tone(100)):e=T.from(this.hue,this.chroma,t).toInt(),this.cache.set(t,e)),e}getHct(t){return T.fromInt(this.tone(t))}averageArgb(t,e){let n=t>>>16&255,a=t>>>8&255,o=t&255,i=e>>>16&255,c=e>>>8&255,f=e&255,g=Math.round((n+i)/2),m=Math.round((a+c)/2),y=Math.round((o+f)/2);return(255<<24|(g&255)<<16|(m&255)<<8|y&255)>>>0}},re=class{constructor(t,e){this.hue=t,this.requestedChroma=e,this.chromaCache=new Map,this.maxChromaValue=200}create(){let a=0,o=100;for(;a<o;){let i=Math.floor((a+o)/2),c=this.maxChroma(i)<this.maxChroma(i+1);if(this.maxChroma(i)>=this.requestedChroma-.01)if(Math.abs(a-50)<Math.abs(o-50))o=i;else{if(a===i)return T.from(this.hue,this.requestedChroma,a);a=i}else c?a=i+1:o=i}return T.from(this.hue,this.requestedChroma,a)}maxChroma(t){if(this.chromaCache.has(t))return this.chromaCache.get(t);let e=T.from(this.hue,this.maxChromaValue,t).chroma;return this.chromaCache.set(t,e),e}};/**
 * @license
 * Copyright 2023 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var St=class r{constructor(t){this.input=t,this.hctsByTempCache=[],this.hctsByHueCache=[],this.tempsByHctCache=new Map,this.inputRelativeTemperatureCache=-1,this.complementCache=null}get hctsByTemp(){if(this.hctsByTempCache.length>0)return this.hctsByTempCache;let t=this.hctsByHue.concat([this.input]),e=this.tempsByHct;return t.sort((n,a)=>e.get(n)-e.get(a)),this.hctsByTempCache=t,t}get warmest(){return this.hctsByTemp[this.hctsByTemp.length-1]}get coldest(){return this.hctsByTemp[0]}analogous(t=5,e=12){let n=Math.round(this.input.hue),a=this.hctsByHue[n],o=this.relativeTemperature(a),i=[a],c=0;for(let p=0;p<360;p++){let l=lt(n+p),C=this.hctsByHue[l],v=this.relativeTemperature(C),S=Math.abs(v-o);o=v,c+=S}let f=1,g=c/e,m=0;for(o=this.relativeTemperature(a);i.length<e;){let p=lt(n+f),l=this.hctsByHue[p],C=this.relativeTemperature(l),v=Math.abs(C-o);m+=v;let S=i.length*g,k=m>=S,I=1;for(;k&&i.length<e;){i.push(l);let L=(i.length+I)*g;k=m>=L,I++}if(o=C,f++,f>360){for(;i.length<e;)i.push(l);break}}let y=[this.input],P=Math.floor((t-1)/2);for(let p=1;p<P+1;p++){let l=0-p;for(;l<0;)l=i.length+l;l>=i.length&&(l=l%i.length),y.splice(0,0,i[l])}let d=t-P-1;for(let p=1;p<d+1;p++){let l=p;for(;l<0;)l=i.length+l;l>=i.length&&(l=l%i.length),y.push(i[l])}return y}get complement(){if(this.complementCache!=null)return this.complementCache;let t=this.coldest.hue,e=this.tempsByHct.get(this.coldest),n=this.warmest.hue,o=this.tempsByHct.get(this.warmest)-e,i=r.isBetween(this.input.hue,t,n),c=i?n:t,f=i?t:n,g=1,m=1e3,y=this.hctsByHue[Math.round(this.input.hue)],P=1-this.inputRelativeTemperature;for(let d=0;d<=360;d+=1){let p=z(c+g*d);if(!r.isBetween(p,c,f))continue;let l=this.hctsByHue[Math.round(p)],C=(this.tempsByHct.get(l)-e)/o,v=Math.abs(P-C);v<m&&(m=v,y=l)}return this.complementCache=y,this.complementCache}relativeTemperature(t){let e=this.tempsByHct.get(this.warmest)-this.tempsByHct.get(this.coldest),n=this.tempsByHct.get(t)-this.tempsByHct.get(this.coldest);return e===0?.5:n/e}get inputRelativeTemperature(){return this.inputRelativeTemperatureCache>=0?this.inputRelativeTemperatureCache:(this.inputRelativeTemperatureCache=this.relativeTemperature(this.input),this.inputRelativeTemperatureCache)}get tempsByHct(){if(this.tempsByHctCache.size>0)return this.tempsByHctCache;let t=this.hctsByHue.concat([this.input]),e=new Map;for(let n of t)e.set(n,r.rawTemperature(n));return this.tempsByHctCache=e,e}get hctsByHue(){if(this.hctsByHueCache.length>0)return this.hctsByHueCache;let t=[];for(let e=0;e<=360;e+=1){let n=T.from(e,this.input.chroma,this.input.tone);t.push(n)}return this.hctsByHueCache=t,this.hctsByHueCache}static isBetween(t,e,n){return e<n?e<=t&&t<=n:e<=t||t<=n}static rawTemperature(t){let e=Ft(t.toInt()),n=z(Math.atan2(e[2],e[1])*180/Math.PI),a=Math.sqrt(e[1]*e[1]+e[2]*e[2]);return-.5+.02*Math.pow(a,1.07)*Math.cos(z(n-50)*Math.PI/180)}};/**
 * @license
 * Copyright 2023 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var D=class{constructor(t,e,n,a){this.low=t,this.normal=e,this.medium=n,this.high=a}get(t){return t<=-1?this.low:t<0?st(this.low,this.normal,(t- -1)/1):t<.5?st(this.normal,this.medium,(t-0)/.5):t<1?st(this.medium,this.high,(t-.5)/.5):this.high}};/**
 * @license
 * Copyright 2023 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var B=class{constructor(t,e,n,a,o,i){this.roleA=t,this.roleB=e,this.delta=n,this.polarity=a,this.stayTogether=o,this.constraint=i,this.constraint=i??"exact"}};/**
 * @license
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var s;(function(r){r[r.MONOCHROME=0]="MONOCHROME",r[r.NEUTRAL=1]="NEUTRAL",r[r.TONAL_SPOT=2]="TONAL_SPOT",r[r.VIBRANT=3]="VIBRANT",r[r.EXPRESSIVE=4]="EXPRESSIVE",r[r.FIDELITY=5]="FIDELITY",r[r.CONTENT=6]="CONTENT",r[r.RAINBOW=7]="RAINBOW",r[r.FRUIT_SALAD=8]="FRUIT_SALAD"})(s||(s={}));/**
 * @license
 * Copyright 2025 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function dt(r){return r.variant===s.FIDELITY||r.variant===s.CONTENT}function N(r){return r.variant===s.MONOCHROME}function Ie(r,t,e,n){let a=e,o=T.from(r,t,e);if(o.chroma<t){let i=o.chroma;for(;o.chroma<t;){a+=n?-1:1;let c=T.from(r,t,a);if(i>c.chroma||Math.abs(c.chroma-t)<.4)break;let f=Math.abs(c.chroma-t),g=Math.abs(o.chroma-t);f<g&&(o=c),i=Math.max(i,c.chroma)}}return a}var vt=class{primaryPaletteKeyColor(){return u.fromPalette({name:"primary_palette_key_color",palette:t=>t.primaryPalette,tone:t=>t.primaryPalette.keyColor.tone})}secondaryPaletteKeyColor(){return u.fromPalette({name:"secondary_palette_key_color",palette:t=>t.secondaryPalette,tone:t=>t.secondaryPalette.keyColor.tone})}tertiaryPaletteKeyColor(){return u.fromPalette({name:"tertiary_palette_key_color",palette:t=>t.tertiaryPalette,tone:t=>t.tertiaryPalette.keyColor.tone})}neutralPaletteKeyColor(){return u.fromPalette({name:"neutral_palette_key_color",palette:t=>t.neutralPalette,tone:t=>t.neutralPalette.keyColor.tone})}neutralVariantPaletteKeyColor(){return u.fromPalette({name:"neutral_variant_palette_key_color",palette:t=>t.neutralVariantPalette,tone:t=>t.neutralVariantPalette.keyColor.tone})}errorPaletteKeyColor(){return u.fromPalette({name:"error_palette_key_color",palette:t=>t.errorPalette,tone:t=>t.errorPalette.keyColor.tone})}background(){return u.fromPalette({name:"background",palette:t=>t.neutralPalette,tone:t=>t.isDark?6:98,isBackground:!0})}onBackground(){return u.fromPalette({name:"on_background",palette:t=>t.neutralPalette,tone:t=>t.isDark?90:10,background:t=>this.background(),contrastCurve:t=>new D(3,3,4.5,7)})}surface(){return u.fromPalette({name:"surface",palette:t=>t.neutralPalette,tone:t=>t.isDark?6:98,isBackground:!0})}surfaceDim(){return u.fromPalette({name:"surface_dim",palette:t=>t.neutralPalette,tone:t=>t.isDark?6:new D(87,87,80,75).get(t.contrastLevel),isBackground:!0})}surfaceBright(){return u.fromPalette({name:"surface_bright",palette:t=>t.neutralPalette,tone:t=>t.isDark?new D(24,24,29,34).get(t.contrastLevel):98,isBackground:!0})}surfaceContainerLowest(){return u.fromPalette({name:"surface_container_lowest",palette:t=>t.neutralPalette,tone:t=>t.isDark?new D(4,4,2,0).get(t.contrastLevel):100,isBackground:!0})}surfaceContainerLow(){return u.fromPalette({name:"surface_container_low",palette:t=>t.neutralPalette,tone:t=>t.isDark?new D(10,10,11,12).get(t.contrastLevel):new D(96,96,96,95).get(t.contrastLevel),isBackground:!0})}surfaceContainer(){return u.fromPalette({name:"surface_container",palette:t=>t.neutralPalette,tone:t=>t.isDark?new D(12,12,16,20).get(t.contrastLevel):new D(94,94,92,90).get(t.contrastLevel),isBackground:!0})}surfaceContainerHigh(){return u.fromPalette({name:"surface_container_high",palette:t=>t.neutralPalette,tone:t=>t.isDark?new D(17,17,21,25).get(t.contrastLevel):new D(92,92,88,85).get(t.contrastLevel),isBackground:!0})}surfaceContainerHighest(){return u.fromPalette({name:"surface_container_highest",palette:t=>t.neutralPalette,tone:t=>t.isDark?new D(22,22,26,30).get(t.contrastLevel):new D(90,90,84,80).get(t.contrastLevel),isBackground:!0})}onSurface(){return u.fromPalette({name:"on_surface",palette:t=>t.neutralPalette,tone:t=>t.isDark?90:10,background:t=>this.highestSurface(t),contrastCurve:t=>new D(4.5,7,11,21)})}surfaceVariant(){return u.fromPalette({name:"surface_variant",palette:t=>t.neutralVariantPalette,tone:t=>t.isDark?30:90,isBackground:!0})}onSurfaceVariant(){return u.fromPalette({name:"on_surface_variant",palette:t=>t.neutralVariantPalette,tone:t=>t.isDark?80:30,background:t=>this.highestSurface(t),contrastCurve:t=>new D(3,4.5,7,11)})}inverseSurface(){return u.fromPalette({name:"inverse_surface",palette:t=>t.neutralPalette,tone:t=>t.isDark?90:20,isBackground:!0})}inverseOnSurface(){return u.fromPalette({name:"inverse_on_surface",palette:t=>t.neutralPalette,tone:t=>t.isDark?20:95,background:t=>this.inverseSurface(),contrastCurve:t=>new D(4.5,7,11,21)})}outline(){return u.fromPalette({name:"outline",palette:t=>t.neutralVariantPalette,tone:t=>t.isDark?60:50,background:t=>this.highestSurface(t),contrastCurve:t=>new D(1.5,3,4.5,7)})}outlineVariant(){return u.fromPalette({name:"outline_variant",palette:t=>t.neutralVariantPalette,tone:t=>t.isDark?30:80,background:t=>this.highestSurface(t),contrastCurve:t=>new D(1,1,3,4.5)})}shadow(){return u.fromPalette({name:"shadow",palette:t=>t.neutralPalette,tone:t=>0})}scrim(){return u.fromPalette({name:"scrim",palette:t=>t.neutralPalette,tone:t=>0})}surfaceTint(){return u.fromPalette({name:"surface_tint",palette:t=>t.primaryPalette,tone:t=>t.isDark?80:40,isBackground:!0})}primary(){return u.fromPalette({name:"primary",palette:t=>t.primaryPalette,tone:t=>N(t)?t.isDark?100:0:t.isDark?80:40,isBackground:!0,background:t=>this.highestSurface(t),contrastCurve:t=>new D(3,4.5,7,7),toneDeltaPair:t=>new B(this.primaryContainer(),this.primary(),10,"nearer",!1)})}primaryDim(){}onPrimary(){return u.fromPalette({name:"on_primary",palette:t=>t.primaryPalette,tone:t=>N(t)?t.isDark?10:90:t.isDark?20:100,background:t=>this.primary(),contrastCurve:t=>new D(4.5,7,11,21)})}primaryContainer(){return u.fromPalette({name:"primary_container",palette:t=>t.primaryPalette,tone:t=>dt(t)?t.sourceColorHct.tone:N(t)?t.isDark?85:25:t.isDark?30:90,isBackground:!0,background:t=>this.highestSurface(t),contrastCurve:t=>new D(1,1,3,4.5),toneDeltaPair:t=>new B(this.primaryContainer(),this.primary(),10,"nearer",!1)})}onPrimaryContainer(){return u.fromPalette({name:"on_primary_container",palette:t=>t.primaryPalette,tone:t=>dt(t)?u.foregroundTone(this.primaryContainer().tone(t),4.5):N(t)?t.isDark?0:100:t.isDark?90:30,background:t=>this.primaryContainer(),contrastCurve:t=>new D(3,4.5,7,11)})}inversePrimary(){return u.fromPalette({name:"inverse_primary",palette:t=>t.primaryPalette,tone:t=>t.isDark?40:80,background:t=>this.inverseSurface(),contrastCurve:t=>new D(3,4.5,7,7)})}secondary(){return u.fromPalette({name:"secondary",palette:t=>t.secondaryPalette,tone:t=>t.isDark?80:40,isBackground:!0,background:t=>this.highestSurface(t),contrastCurve:t=>new D(3,4.5,7,7),toneDeltaPair:t=>new B(this.secondaryContainer(),this.secondary(),10,"nearer",!1)})}secondaryDim(){}onSecondary(){return u.fromPalette({name:"on_secondary",palette:t=>t.secondaryPalette,tone:t=>N(t)?t.isDark?10:100:t.isDark?20:100,background:t=>this.secondary(),contrastCurve:t=>new D(4.5,7,11,21)})}secondaryContainer(){return u.fromPalette({name:"secondary_container",palette:t=>t.secondaryPalette,tone:t=>{let e=t.isDark?30:90;return N(t)?t.isDark?30:85:dt(t)?Ie(t.secondaryPalette.hue,t.secondaryPalette.chroma,e,!t.isDark):e},isBackground:!0,background:t=>this.highestSurface(t),contrastCurve:t=>new D(1,1,3,4.5),toneDeltaPair:t=>new B(this.secondaryContainer(),this.secondary(),10,"nearer",!1)})}onSecondaryContainer(){return u.fromPalette({name:"on_secondary_container",palette:t=>t.secondaryPalette,tone:t=>N(t)?t.isDark?90:10:dt(t)?u.foregroundTone(this.secondaryContainer().tone(t),4.5):t.isDark?90:30,background:t=>this.secondaryContainer(),contrastCurve:t=>new D(3,4.5,7,11)})}tertiary(){return u.fromPalette({name:"tertiary",palette:t=>t.tertiaryPalette,tone:t=>N(t)?t.isDark?90:25:t.isDark?80:40,isBackground:!0,background:t=>this.highestSurface(t),contrastCurve:t=>new D(3,4.5,7,7),toneDeltaPair:t=>new B(this.tertiaryContainer(),this.tertiary(),10,"nearer",!1)})}tertiaryDim(){}onTertiary(){return u.fromPalette({name:"on_tertiary",palette:t=>t.tertiaryPalette,tone:t=>N(t)?t.isDark?10:90:t.isDark?20:100,background:t=>this.tertiary(),contrastCurve:t=>new D(4.5,7,11,21)})}tertiaryContainer(){return u.fromPalette({name:"tertiary_container",palette:t=>t.tertiaryPalette,tone:t=>{if(N(t))return t.isDark?60:49;if(!dt(t))return t.isDark?30:90;let e=t.tertiaryPalette.getHct(t.sourceColorHct.tone);return ut.fixIfDisliked(e).tone},isBackground:!0,background:t=>this.highestSurface(t),contrastCurve:t=>new D(1,1,3,4.5),toneDeltaPair:t=>new B(this.tertiaryContainer(),this.tertiary(),10,"nearer",!1)})}onTertiaryContainer(){return u.fromPalette({name:"on_tertiary_container",palette:t=>t.tertiaryPalette,tone:t=>N(t)?t.isDark?0:100:dt(t)?u.foregroundTone(this.tertiaryContainer().tone(t),4.5):t.isDark?90:30,background:t=>this.tertiaryContainer(),contrastCurve:t=>new D(3,4.5,7,11)})}error(){return u.fromPalette({name:"error",palette:t=>t.errorPalette,tone:t=>t.isDark?80:40,isBackground:!0,background:t=>this.highestSurface(t),contrastCurve:t=>new D(3,4.5,7,7),toneDeltaPair:t=>new B(this.errorContainer(),this.error(),10,"nearer",!1)})}errorDim(){}onError(){return u.fromPalette({name:"on_error",palette:t=>t.errorPalette,tone:t=>t.isDark?20:100,background:t=>this.error(),contrastCurve:t=>new D(4.5,7,11,21)})}errorContainer(){return u.fromPalette({name:"error_container",palette:t=>t.errorPalette,tone:t=>t.isDark?30:90,isBackground:!0,background:t=>this.highestSurface(t),contrastCurve:t=>new D(1,1,3,4.5),toneDeltaPair:t=>new B(this.errorContainer(),this.error(),10,"nearer",!1)})}onErrorContainer(){return u.fromPalette({name:"on_error_container",palette:t=>t.errorPalette,tone:t=>N(t)?t.isDark?90:10:t.isDark?90:30,background:t=>this.errorContainer(),contrastCurve:t=>new D(3,4.5,7,11)})}primaryFixed(){return u.fromPalette({name:"primary_fixed",palette:t=>t.primaryPalette,tone:t=>N(t)?40:90,isBackground:!0,background:t=>this.highestSurface(t),contrastCurve:t=>new D(1,1,3,4.5),toneDeltaPair:t=>new B(this.primaryFixed(),this.primaryFixedDim(),10,"lighter",!0)})}primaryFixedDim(){return u.fromPalette({name:"primary_fixed_dim",palette:t=>t.primaryPalette,tone:t=>N(t)?30:80,isBackground:!0,background:t=>this.highestSurface(t),contrastCurve:t=>new D(1,1,3,4.5),toneDeltaPair:t=>new B(this.primaryFixed(),this.primaryFixedDim(),10,"lighter",!0)})}onPrimaryFixed(){return u.fromPalette({name:"on_primary_fixed",palette:t=>t.primaryPalette,tone:t=>N(t)?100:10,background:t=>this.primaryFixedDim(),secondBackground:t=>this.primaryFixed(),contrastCurve:t=>new D(4.5,7,11,21)})}onPrimaryFixedVariant(){return u.fromPalette({name:"on_primary_fixed_variant",palette:t=>t.primaryPalette,tone:t=>N(t)?90:30,background:t=>this.primaryFixedDim(),secondBackground:t=>this.primaryFixed(),contrastCurve:t=>new D(3,4.5,7,11)})}secondaryFixed(){return u.fromPalette({name:"secondary_fixed",palette:t=>t.secondaryPalette,tone:t=>N(t)?80:90,isBackground:!0,background:t=>this.highestSurface(t),contrastCurve:t=>new D(1,1,3,4.5),toneDeltaPair:t=>new B(this.secondaryFixed(),this.secondaryFixedDim(),10,"lighter",!0)})}secondaryFixedDim(){return u.fromPalette({name:"secondary_fixed_dim",palette:t=>t.secondaryPalette,tone:t=>N(t)?70:80,isBackground:!0,background:t=>this.highestSurface(t),contrastCurve:t=>new D(1,1,3,4.5),toneDeltaPair:t=>new B(this.secondaryFixed(),this.secondaryFixedDim(),10,"lighter",!0)})}onSecondaryFixed(){return u.fromPalette({name:"on_secondary_fixed",palette:t=>t.secondaryPalette,tone:t=>10,background:t=>this.secondaryFixedDim(),secondBackground:t=>this.secondaryFixed(),contrastCurve:t=>new D(4.5,7,11,21)})}onSecondaryFixedVariant(){return u.fromPalette({name:"on_secondary_fixed_variant",palette:t=>t.secondaryPalette,tone:t=>N(t)?25:30,background:t=>this.secondaryFixedDim(),secondBackground:t=>this.secondaryFixed(),contrastCurve:t=>new D(3,4.5,7,11)})}tertiaryFixed(){return u.fromPalette({name:"tertiary_fixed",palette:t=>t.tertiaryPalette,tone:t=>N(t)?40:90,isBackground:!0,background:t=>this.highestSurface(t),contrastCurve:t=>new D(1,1,3,4.5),toneDeltaPair:t=>new B(this.tertiaryFixed(),this.tertiaryFixedDim(),10,"lighter",!0)})}tertiaryFixedDim(){return u.fromPalette({name:"tertiary_fixed_dim",palette:t=>t.tertiaryPalette,tone:t=>N(t)?30:80,isBackground:!0,background:t=>this.highestSurface(t),contrastCurve:t=>new D(1,1,3,4.5),toneDeltaPair:t=>new B(this.tertiaryFixed(),this.tertiaryFixedDim(),10,"lighter",!0)})}onTertiaryFixed(){return u.fromPalette({name:"on_tertiary_fixed",palette:t=>t.tertiaryPalette,tone:t=>N(t)?100:10,background:t=>this.tertiaryFixedDim(),secondBackground:t=>this.tertiaryFixed(),contrastCurve:t=>new D(4.5,7,11,21)})}onTertiaryFixedVariant(){return u.fromPalette({name:"on_tertiary_fixed_variant",palette:t=>t.tertiaryPalette,tone:t=>N(t)?90:30,background:t=>this.tertiaryFixedDim(),secondBackground:t=>this.tertiaryFixed(),contrastCurve:t=>new D(3,4.5,7,11)})}highestSurface(t){return t.isDark?this.surfaceBright():this.surfaceDim()}};/**
 * @license
 * Copyright 2025 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function M(r,t=0,e=100,n=1){let a=Ce(r.hue,r.chroma*n,100,!0);return U(t,e,a)}function ot(r,t=0,e=100){let n=Ce(r.hue,r.chroma,0,!1);return U(t,e,n)}function Ce(r,t,e,n){let a=e,o=T.from(r,t,a);for(;o.chroma<t&&!(e<0||e>100);){e+=n?-1:1;let i=T.from(r,t,e);o.chroma<i.chroma&&(o=i,a=e)}return a}function b(r){return r===1.5?new D(1.5,1.5,3,5.5):r===3?new D(3,3,4.5,7):r===4.5?new D(4.5,4.5,7,11):r===6?new D(6,6,7,11):r===7?new D(7,7,11,21):r===9?new D(9,9,11,21):r===11?new D(11,11,21,21):r===21?new D(21,21,21,21):new D(r,r,7,21)}var Et=class extends vt{surface(){let t=u.fromPalette({name:"surface",palette:e=>e.neutralPalette,tone:e=>(super.surface().tone(e),e.platform==="phone"?e.isDark?4:T.isYellow(e.neutralPalette.hue)?99:e.variant===s.VIBRANT?97:98:0),isBackground:!0});return w(super.surface(),"2025",t)}surfaceDim(){let t=u.fromPalette({name:"surface_dim",palette:e=>e.neutralPalette,tone:e=>e.isDark?4:T.isYellow(e.neutralPalette.hue)?90:e.variant===s.VIBRANT?85:87,isBackground:!0,chromaMultiplier:e=>{if(!e.isDark){if(e.variant===s.NEUTRAL)return 2.5;if(e.variant===s.TONAL_SPOT)return 1.7;if(e.variant===s.EXPRESSIVE)return T.isYellow(e.neutralPalette.hue)?2.7:1.75;if(e.variant===s.VIBRANT)return 1.36}return 1}});return w(super.surfaceDim(),"2025",t)}surfaceBright(){let t=u.fromPalette({name:"surface_bright",palette:e=>e.neutralPalette,tone:e=>e.isDark?18:T.isYellow(e.neutralPalette.hue)?99:e.variant===s.VIBRANT?97:98,isBackground:!0,chromaMultiplier:e=>{if(e.isDark){if(e.variant===s.NEUTRAL)return 2.5;if(e.variant===s.TONAL_SPOT)return 1.7;if(e.variant===s.EXPRESSIVE)return T.isYellow(e.neutralPalette.hue)?2.7:1.75;if(e.variant===s.VIBRANT)return 1.36}return 1}});return w(super.surfaceBright(),"2025",t)}surfaceContainerLowest(){let t=u.fromPalette({name:"surface_container_lowest",palette:e=>e.neutralPalette,tone:e=>e.isDark?0:100,isBackground:!0});return w(super.surfaceContainerLowest(),"2025",t)}surfaceContainerLow(){let t=u.fromPalette({name:"surface_container_low",palette:e=>e.neutralPalette,tone:e=>e.platform==="phone"?e.isDark?6:T.isYellow(e.neutralPalette.hue)?98:e.variant===s.VIBRANT?95:96:15,isBackground:!0,chromaMultiplier:e=>{if(e.platform==="phone"){if(e.variant===s.NEUTRAL)return 1.3;if(e.variant===s.TONAL_SPOT)return 1.25;if(e.variant===s.EXPRESSIVE)return T.isYellow(e.neutralPalette.hue)?1.3:1.15;if(e.variant===s.VIBRANT)return 1.08}return 1}});return w(super.surfaceContainerLow(),"2025",t)}surfaceContainer(){let t=u.fromPalette({name:"surface_container",palette:e=>e.neutralPalette,tone:e=>e.platform==="phone"?e.isDark?9:T.isYellow(e.neutralPalette.hue)?96:e.variant===s.VIBRANT?92:94:20,isBackground:!0,chromaMultiplier:e=>{if(e.platform==="phone"){if(e.variant===s.NEUTRAL)return 1.6;if(e.variant===s.TONAL_SPOT)return 1.4;if(e.variant===s.EXPRESSIVE)return T.isYellow(e.neutralPalette.hue)?1.6:1.3;if(e.variant===s.VIBRANT)return 1.15}return 1}});return w(super.surfaceContainer(),"2025",t)}surfaceContainerHigh(){let t=u.fromPalette({name:"surface_container_high",palette:e=>e.neutralPalette,tone:e=>e.platform==="phone"?e.isDark?12:T.isYellow(e.neutralPalette.hue)?94:e.variant===s.VIBRANT?90:92:25,isBackground:!0,chromaMultiplier:e=>{if(e.platform==="phone"){if(e.variant===s.NEUTRAL)return 1.9;if(e.variant===s.TONAL_SPOT)return 1.5;if(e.variant===s.EXPRESSIVE)return T.isYellow(e.neutralPalette.hue)?1.95:1.45;if(e.variant===s.VIBRANT)return 1.22}return 1}});return w(super.surfaceContainerHigh(),"2025",t)}surfaceContainerHighest(){let t=u.fromPalette({name:"surface_container_highest",palette:e=>e.neutralPalette,tone:e=>e.isDark?15:T.isYellow(e.neutralPalette.hue)?92:e.variant===s.VIBRANT?88:90,isBackground:!0,chromaMultiplier:e=>e.variant===s.NEUTRAL?2.2:e.variant===s.TONAL_SPOT?1.7:e.variant===s.EXPRESSIVE?T.isYellow(e.neutralPalette.hue)?2.3:1.6:e.variant===s.VIBRANT?1.29:1});return w(super.surfaceContainerHighest(),"2025",t)}onSurface(){let t=u.fromPalette({name:"on_surface",palette:e=>e.neutralPalette,tone:e=>e.variant===s.VIBRANT?M(e.neutralPalette,0,100,1.1):u.getInitialToneFromBackground(n=>n.platform==="phone"?this.highestSurface(n):this.surfaceContainerHigh())(e),chromaMultiplier:e=>{if(e.platform==="phone"){if(e.variant===s.NEUTRAL)return 2.2;if(e.variant===s.TONAL_SPOT)return 1.7;if(e.variant===s.EXPRESSIVE)return T.isYellow(e.neutralPalette.hue)?e.isDark?3:2.3:1.6}return 1},background:e=>e.platform==="phone"?this.highestSurface(e):this.surfaceContainerHigh(),contrastCurve:e=>e.isDark&&e.platform==="phone"?b(11):b(9)});return w(super.onSurface(),"2025",t)}onSurfaceVariant(){let t=u.fromPalette({name:"on_surface_variant",palette:e=>e.neutralPalette,chromaMultiplier:e=>{if(e.platform==="phone"){if(e.variant===s.NEUTRAL)return 2.2;if(e.variant===s.TONAL_SPOT)return 1.7;if(e.variant===s.EXPRESSIVE)return T.isYellow(e.neutralPalette.hue)?e.isDark?3:2.3:1.6}return 1},background:e=>e.platform==="phone"?this.highestSurface(e):this.surfaceContainerHigh(),contrastCurve:e=>e.platform==="phone"?e.isDark?b(6):b(4.5):b(7)});return w(super.onSurfaceVariant(),"2025",t)}outline(){let t=u.fromPalette({name:"outline",palette:e=>e.neutralPalette,chromaMultiplier:e=>{if(e.platform==="phone"){if(e.variant===s.NEUTRAL)return 2.2;if(e.variant===s.TONAL_SPOT)return 1.7;if(e.variant===s.EXPRESSIVE)return T.isYellow(e.neutralPalette.hue)?e.isDark?3:2.3:1.6}return 1},background:e=>e.platform==="phone"?this.highestSurface(e):this.surfaceContainerHigh(),contrastCurve:e=>e.platform==="phone"?b(3):b(4.5)});return w(super.outline(),"2025",t)}outlineVariant(){let t=u.fromPalette({name:"outline_variant",palette:e=>e.neutralPalette,chromaMultiplier:e=>{if(e.platform==="phone"){if(e.variant===s.NEUTRAL)return 2.2;if(e.variant===s.TONAL_SPOT)return 1.7;if(e.variant===s.EXPRESSIVE)return T.isYellow(e.neutralPalette.hue)?e.isDark?3:2.3:1.6}return 1},background:e=>e.platform==="phone"?this.highestSurface(e):this.surfaceContainerHigh(),contrastCurve:e=>e.platform==="phone"?b(1.5):b(3)});return w(super.outlineVariant(),"2025",t)}inverseSurface(){let t=u.fromPalette({name:"inverse_surface",palette:e=>e.neutralPalette,tone:e=>e.isDark?98:4,isBackground:!0});return w(super.inverseSurface(),"2025",t)}inverseOnSurface(){let t=u.fromPalette({name:"inverse_on_surface",palette:e=>e.neutralPalette,background:e=>this.inverseSurface(),contrastCurve:e=>b(7)});return w(super.inverseOnSurface(),"2025",t)}primary(){let t=u.fromPalette({name:"primary",palette:e=>e.primaryPalette,tone:e=>e.variant===s.NEUTRAL?e.platform==="phone"?e.isDark?80:40:90:e.variant===s.TONAL_SPOT?e.platform==="phone"?e.isDark?80:M(e.primaryPalette):M(e.primaryPalette,0,90):e.variant===s.EXPRESSIVE?e.platform==="phone"?M(e.primaryPalette,0,T.isYellow(e.primaryPalette.hue)?25:T.isCyan(e.primaryPalette.hue)?88:98):M(e.primaryPalette):e.platform==="phone"?M(e.primaryPalette,0,T.isCyan(e.primaryPalette.hue)?88:98):M(e.primaryPalette),isBackground:!0,background:e=>e.platform==="phone"?this.highestSurface(e):this.surfaceContainerHigh(),contrastCurve:e=>e.platform==="phone"?b(4.5):b(7),toneDeltaPair:e=>e.platform==="phone"?new B(this.primaryContainer(),this.primary(),5,"relative_lighter",!0,"farther"):void 0});return w(super.primary(),"2025",t)}primaryDim(){return u.fromPalette({name:"primary_dim",palette:t=>t.primaryPalette,tone:t=>t.variant===s.NEUTRAL?85:t.variant===s.TONAL_SPOT?M(t.primaryPalette,0,90):M(t.primaryPalette),isBackground:!0,background:t=>this.surfaceContainerHigh(),contrastCurve:t=>b(4.5),toneDeltaPair:t=>new B(this.primaryDim(),this.primary(),5,"darker",!0,"farther")})}onPrimary(){let t=u.fromPalette({name:"on_primary",palette:e=>e.primaryPalette,background:e=>e.platform==="phone"?this.primary():this.primaryDim(),contrastCurve:e=>e.platform==="phone"?b(6):b(7)});return w(super.onPrimary(),"2025",t)}primaryContainer(){let t=u.fromPalette({name:"primary_container",palette:e=>e.primaryPalette,tone:e=>e.platform==="watch"?30:e.variant===s.NEUTRAL?e.isDark?30:90:e.variant===s.TONAL_SPOT?e.isDark?ot(e.primaryPalette,35,93):M(e.primaryPalette,0,90):e.variant===s.EXPRESSIVE?e.isDark?M(e.primaryPalette,30,93):M(e.primaryPalette,78,T.isCyan(e.primaryPalette.hue)?88:90):e.isDark?ot(e.primaryPalette,66,93):M(e.primaryPalette,66,T.isCyan(e.primaryPalette.hue)?88:93),isBackground:!0,background:e=>e.platform==="phone"?this.highestSurface(e):void 0,toneDeltaPair:e=>e.platform==="phone"?void 0:new B(this.primaryContainer(),this.primaryDim(),10,"darker",!0,"farther"),contrastCurve:e=>e.platform==="phone"&&e.contrastLevel>0?b(1.5):void 0});return w(super.primaryContainer(),"2025",t)}onPrimaryContainer(){let t=u.fromPalette({name:"on_primary_container",palette:e=>e.primaryPalette,background:e=>this.primaryContainer(),contrastCurve:e=>e.platform==="phone"?b(6):b(7)});return w(super.onPrimaryContainer(),"2025",t)}primaryFixed(){let t=u.fromPalette({name:"primary_fixed",palette:e=>e.primaryPalette,tone:e=>{let n=Object.assign({},e,{isDark:!1,contrastLevel:0});return this.primaryContainer().getTone(n)},isBackground:!0,background:e=>e.platform==="phone"?this.highestSurface(e):void 0,contrastCurve:e=>e.platform==="phone"&&e.contrastLevel>0?b(1.5):void 0});return w(super.primaryFixed(),"2025",t)}primaryFixedDim(){let t=u.fromPalette({name:"primary_fixed_dim",palette:e=>e.primaryPalette,tone:e=>this.primaryFixed().getTone(e),isBackground:!0,toneDeltaPair:e=>new B(this.primaryFixedDim(),this.primaryFixed(),5,"darker",!0,"exact")});return w(super.primaryFixedDim(),"2025",t)}onPrimaryFixed(){let t=u.fromPalette({name:"on_primary_fixed",palette:e=>e.primaryPalette,background:e=>this.primaryFixedDim(),contrastCurve:e=>b(7)});return w(super.onPrimaryFixed(),"2025",t)}onPrimaryFixedVariant(){let t=u.fromPalette({name:"on_primary_fixed_variant",palette:e=>e.primaryPalette,background:e=>this.primaryFixedDim(),contrastCurve:e=>b(4.5)});return w(super.onPrimaryFixedVariant(),"2025",t)}inversePrimary(){let t=u.fromPalette({name:"inverse_primary",palette:e=>e.primaryPalette,tone:e=>M(e.primaryPalette),background:e=>this.inverseSurface(),contrastCurve:e=>e.platform==="phone"?b(6):b(7)});return w(super.inversePrimary(),"2025",t)}secondary(){let t=u.fromPalette({name:"secondary",palette:e=>e.secondaryPalette,tone:e=>e.platform==="watch"?e.variant===s.NEUTRAL?90:M(e.secondaryPalette,0,90):e.variant===s.NEUTRAL?e.isDark?ot(e.secondaryPalette,0,98):M(e.secondaryPalette):e.variant===s.VIBRANT?M(e.secondaryPalette,0,e.isDark?90:98):e.isDark?80:M(e.secondaryPalette),isBackground:!0,background:e=>e.platform==="phone"?this.highestSurface(e):this.surfaceContainerHigh(),contrastCurve:e=>e.platform==="phone"?b(4.5):b(7),toneDeltaPair:e=>e.platform==="phone"?new B(this.secondaryContainer(),this.secondary(),5,"relative_lighter",!0,"farther"):void 0});return w(super.secondary(),"2025",t)}secondaryDim(){return u.fromPalette({name:"secondary_dim",palette:t=>t.secondaryPalette,tone:t=>t.variant===s.NEUTRAL?85:M(t.secondaryPalette,0,90),isBackground:!0,background:t=>this.surfaceContainerHigh(),contrastCurve:t=>b(4.5),toneDeltaPair:t=>new B(this.secondaryDim(),this.secondary(),5,"darker",!0,"farther")})}onSecondary(){let t=u.fromPalette({name:"on_secondary",palette:e=>e.secondaryPalette,background:e=>e.platform==="phone"?this.secondary():this.secondaryDim(),contrastCurve:e=>e.platform==="phone"?b(6):b(7)});return w(super.onSecondary(),"2025",t)}secondaryContainer(){let t=u.fromPalette({name:"secondary_container",palette:e=>e.secondaryPalette,tone:e=>e.platform==="watch"?30:e.variant===s.VIBRANT?e.isDark?ot(e.secondaryPalette,30,40):M(e.secondaryPalette,84,90):e.variant===s.EXPRESSIVE?e.isDark?15:M(e.secondaryPalette,90,95):e.isDark?25:90,isBackground:!0,background:e=>e.platform==="phone"?this.highestSurface(e):void 0,toneDeltaPair:e=>e.platform==="watch"?new B(this.secondaryContainer(),this.secondaryDim(),10,"darker",!0,"farther"):void 0,contrastCurve:e=>e.platform==="phone"&&e.contrastLevel>0?b(1.5):void 0});return w(super.secondaryContainer(),"2025",t)}onSecondaryContainer(){let t=u.fromPalette({name:"on_secondary_container",palette:e=>e.secondaryPalette,background:e=>this.secondaryContainer(),contrastCurve:e=>e.platform==="phone"?b(6):b(7)});return w(super.onSecondaryContainer(),"2025",t)}secondaryFixed(){let t=u.fromPalette({name:"secondary_fixed",palette:e=>e.secondaryPalette,tone:e=>{let n=Object.assign({},e,{isDark:!1,contrastLevel:0});return this.secondaryContainer().getTone(n)},isBackground:!0,background:e=>e.platform==="phone"?this.highestSurface(e):void 0,contrastCurve:e=>e.platform==="phone"&&e.contrastLevel>0?b(1.5):void 0});return w(super.secondaryFixed(),"2025",t)}secondaryFixedDim(){let t=u.fromPalette({name:"secondary_fixed_dim",palette:e=>e.secondaryPalette,tone:e=>this.secondaryFixed().getTone(e),isBackground:!0,toneDeltaPair:e=>new B(this.secondaryFixedDim(),this.secondaryFixed(),5,"darker",!0,"exact")});return w(super.secondaryFixedDim(),"2025",t)}onSecondaryFixed(){let t=u.fromPalette({name:"on_secondary_fixed",palette:e=>e.secondaryPalette,background:e=>this.secondaryFixedDim(),contrastCurve:e=>b(7)});return w(super.onSecondaryFixed(),"2025",t)}onSecondaryFixedVariant(){let t=u.fromPalette({name:"on_secondary_fixed_variant",palette:e=>e.secondaryPalette,background:e=>this.secondaryFixedDim(),contrastCurve:e=>b(4.5)});return w(super.onSecondaryFixedVariant(),"2025",t)}tertiary(){let t=u.fromPalette({name:"tertiary",palette:e=>e.tertiaryPalette,tone:e=>e.platform==="watch"?e.variant===s.TONAL_SPOT?M(e.tertiaryPalette,0,90):M(e.tertiaryPalette):e.variant===s.EXPRESSIVE||e.variant===s.VIBRANT?M(e.tertiaryPalette,0,T.isCyan(e.tertiaryPalette.hue)?88:e.isDark?98:100):e.isDark?M(e.tertiaryPalette,0,98):M(e.tertiaryPalette),isBackground:!0,background:e=>e.platform==="phone"?this.highestSurface(e):this.surfaceContainerHigh(),contrastCurve:e=>e.platform==="phone"?b(4.5):b(7),toneDeltaPair:e=>e.platform==="phone"?new B(this.tertiaryContainer(),this.tertiary(),5,"relative_lighter",!0,"farther"):void 0});return w(super.tertiary(),"2025",t)}tertiaryDim(){return u.fromPalette({name:"tertiary_dim",palette:t=>t.tertiaryPalette,tone:t=>t.variant===s.TONAL_SPOT?M(t.tertiaryPalette,0,90):M(t.tertiaryPalette),isBackground:!0,background:t=>this.surfaceContainerHigh(),contrastCurve:t=>b(4.5),toneDeltaPair:t=>new B(this.tertiaryDim(),this.tertiary(),5,"darker",!0,"farther")})}onTertiary(){let t=u.fromPalette({name:"on_tertiary",palette:e=>e.tertiaryPalette,background:e=>e.platform==="phone"?this.tertiary():this.tertiaryDim(),contrastCurve:e=>e.platform==="phone"?b(6):b(7)});return w(super.onTertiary(),"2025",t)}tertiaryContainer(){let t=u.fromPalette({name:"tertiary_container",palette:e=>e.tertiaryPalette,tone:e=>e.platform==="watch"?e.variant===s.TONAL_SPOT?M(e.tertiaryPalette,0,90):M(e.tertiaryPalette):e.variant===s.NEUTRAL?e.isDark?M(e.tertiaryPalette,0,93):M(e.tertiaryPalette,0,96):e.variant===s.TONAL_SPOT?M(e.tertiaryPalette,0,e.isDark?93:100):e.variant===s.EXPRESSIVE?M(e.tertiaryPalette,75,T.isCyan(e.tertiaryPalette.hue)?88:e.isDark?93:100):e.isDark?M(e.tertiaryPalette,0,93):M(e.tertiaryPalette,72,100),isBackground:!0,background:e=>e.platform==="phone"?this.highestSurface(e):void 0,toneDeltaPair:e=>e.platform==="watch"?new B(this.tertiaryContainer(),this.tertiaryDim(),10,"darker",!0,"farther"):void 0,contrastCurve:e=>e.platform==="phone"&&e.contrastLevel>0?b(1.5):void 0});return w(super.tertiaryContainer(),"2025",t)}onTertiaryContainer(){let t=u.fromPalette({name:"on_tertiary_container",palette:e=>e.tertiaryPalette,background:e=>this.tertiaryContainer(),contrastCurve:e=>e.platform==="phone"?b(6):b(7)});return w(super.onTertiaryContainer(),"2025",t)}tertiaryFixed(){let t=u.fromPalette({name:"tertiary_fixed",palette:e=>e.tertiaryPalette,tone:e=>{let n=Object.assign({},e,{isDark:!1,contrastLevel:0});return this.tertiaryContainer().getTone(n)},isBackground:!0,background:e=>e.platform==="phone"?this.highestSurface(e):void 0,contrastCurve:e=>e.platform==="phone"&&e.contrastLevel>0?b(1.5):void 0});return w(super.tertiaryFixed(),"2025",t)}tertiaryFixedDim(){let t=u.fromPalette({name:"tertiary_fixed_dim",palette:e=>e.tertiaryPalette,tone:e=>this.tertiaryFixed().getTone(e),isBackground:!0,toneDeltaPair:e=>new B(this.tertiaryFixedDim(),this.tertiaryFixed(),5,"darker",!0,"exact")});return w(super.tertiaryFixedDim(),"2025",t)}onTertiaryFixed(){let t=u.fromPalette({name:"on_tertiary_fixed",palette:e=>e.tertiaryPalette,background:e=>this.tertiaryFixedDim(),contrastCurve:e=>b(7)});return w(super.onTertiaryFixed(),"2025",t)}onTertiaryFixedVariant(){let t=u.fromPalette({name:"on_tertiary_fixed_variant",palette:e=>e.tertiaryPalette,background:e=>this.tertiaryFixedDim(),contrastCurve:e=>b(4.5)});return w(super.onTertiaryFixedVariant(),"2025",t)}error(){let t=u.fromPalette({name:"error",palette:e=>e.errorPalette,tone:e=>e.platform==="phone"?e.isDark?ot(e.errorPalette,0,98):M(e.errorPalette):ot(e.errorPalette),isBackground:!0,background:e=>e.platform==="phone"?this.highestSurface(e):this.surfaceContainerHigh(),contrastCurve:e=>e.platform==="phone"?b(4.5):b(7),toneDeltaPair:e=>e.platform==="phone"?new B(this.errorContainer(),this.error(),5,"relative_lighter",!0,"farther"):void 0});return w(super.error(),"2025",t)}errorDim(){return u.fromPalette({name:"error_dim",palette:t=>t.errorPalette,tone:t=>ot(t.errorPalette),isBackground:!0,background:t=>this.surfaceContainerHigh(),contrastCurve:t=>b(4.5),toneDeltaPair:t=>new B(this.errorDim(),this.error(),5,"darker",!0,"farther")})}onError(){let t=u.fromPalette({name:"on_error",palette:e=>e.errorPalette,background:e=>e.platform==="phone"?this.error():this.errorDim(),contrastCurve:e=>e.platform==="phone"?b(6):b(7)});return w(super.onError(),"2025",t)}errorContainer(){let t=u.fromPalette({name:"error_container",palette:e=>e.errorPalette,tone:e=>e.platform==="watch"?30:e.isDark?ot(e.errorPalette,30,93):M(e.errorPalette,0,90),isBackground:!0,background:e=>e.platform==="phone"?this.highestSurface(e):void 0,toneDeltaPair:e=>e.platform==="watch"?new B(this.errorContainer(),this.errorDim(),10,"darker",!0,"farther"):void 0,contrastCurve:e=>e.platform==="phone"&&e.contrastLevel>0?b(1.5):void 0});return w(super.errorContainer(),"2025",t)}onErrorContainer(){let t=u.fromPalette({name:"on_error_container",palette:e=>e.errorPalette,background:e=>this.errorContainer(),contrastCurve:e=>e.platform==="phone"?b(4.5):b(7)});return w(super.onErrorContainer(),"2025",t)}surfaceVariant(){let t=Object.assign(this.surfaceContainerHighest().clone(),{name:"surface_variant"});return w(super.surfaceVariant(),"2025",t)}surfaceTint(){let t=Object.assign(this.primary().clone(),{name:"surface_tint"});return w(super.surfaceTint(),"2025",t)}background(){let t=Object.assign(this.surface().clone(),{name:"background"});return w(super.background(),"2025",t)}onBackground(){let t=Object.assign(this.onSurface().clone(),{name:"on_background",tone:e=>e.platform==="watch"?100:this.onSurface().getTone(e)});return w(super.onBackground(),"2025",t)}};/**
 * @license
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var h=class r{constructor(){this.allColors=[this.background(),this.onBackground(),this.surface(),this.surfaceDim(),this.surfaceBright(),this.surfaceContainerLowest(),this.surfaceContainerLow(),this.surfaceContainer(),this.surfaceContainerHigh(),this.surfaceContainerHighest(),this.onSurface(),this.onSurfaceVariant(),this.outline(),this.outlineVariant(),this.inverseSurface(),this.inverseOnSurface(),this.primary(),this.primaryDim(),this.onPrimary(),this.primaryContainer(),this.onPrimaryContainer(),this.primaryFixed(),this.primaryFixedDim(),this.onPrimaryFixed(),this.onPrimaryFixedVariant(),this.inversePrimary(),this.secondary(),this.secondaryDim(),this.onSecondary(),this.secondaryContainer(),this.onSecondaryContainer(),this.secondaryFixed(),this.secondaryFixedDim(),this.onSecondaryFixed(),this.onSecondaryFixedVariant(),this.tertiary(),this.tertiaryDim(),this.onTertiary(),this.tertiaryContainer(),this.onTertiaryContainer(),this.tertiaryFixed(),this.tertiaryFixedDim(),this.onTertiaryFixed(),this.onTertiaryFixedVariant(),this.error(),this.errorDim(),this.onError(),this.errorContainer(),this.onErrorContainer()].filter(t=>t!==void 0)}highestSurface(t){return r.colorSpec.highestSurface(t)}primaryPaletteKeyColor(){return r.colorSpec.primaryPaletteKeyColor()}secondaryPaletteKeyColor(){return r.colorSpec.secondaryPaletteKeyColor()}tertiaryPaletteKeyColor(){return r.colorSpec.tertiaryPaletteKeyColor()}neutralPaletteKeyColor(){return r.colorSpec.neutralPaletteKeyColor()}neutralVariantPaletteKeyColor(){return r.colorSpec.neutralVariantPaletteKeyColor()}errorPaletteKeyColor(){return r.colorSpec.errorPaletteKeyColor()}background(){return r.colorSpec.background()}onBackground(){return r.colorSpec.onBackground()}surface(){return r.colorSpec.surface()}surfaceDim(){return r.colorSpec.surfaceDim()}surfaceBright(){return r.colorSpec.surfaceBright()}surfaceContainerLowest(){return r.colorSpec.surfaceContainerLowest()}surfaceContainerLow(){return r.colorSpec.surfaceContainerLow()}surfaceContainer(){return r.colorSpec.surfaceContainer()}surfaceContainerHigh(){return r.colorSpec.surfaceContainerHigh()}surfaceContainerHighest(){return r.colorSpec.surfaceContainerHighest()}onSurface(){return r.colorSpec.onSurface()}surfaceVariant(){return r.colorSpec.surfaceVariant()}onSurfaceVariant(){return r.colorSpec.onSurfaceVariant()}outline(){return r.colorSpec.outline()}outlineVariant(){return r.colorSpec.outlineVariant()}inverseSurface(){return r.colorSpec.inverseSurface()}inverseOnSurface(){return r.colorSpec.inverseOnSurface()}shadow(){return r.colorSpec.shadow()}scrim(){return r.colorSpec.scrim()}surfaceTint(){return r.colorSpec.surfaceTint()}primary(){return r.colorSpec.primary()}primaryDim(){return r.colorSpec.primaryDim()}onPrimary(){return r.colorSpec.onPrimary()}primaryContainer(){return r.colorSpec.primaryContainer()}onPrimaryContainer(){return r.colorSpec.onPrimaryContainer()}inversePrimary(){return r.colorSpec.inversePrimary()}primaryFixed(){return r.colorSpec.primaryFixed()}primaryFixedDim(){return r.colorSpec.primaryFixedDim()}onPrimaryFixed(){return r.colorSpec.onPrimaryFixed()}onPrimaryFixedVariant(){return r.colorSpec.onPrimaryFixedVariant()}secondary(){return r.colorSpec.secondary()}secondaryDim(){return r.colorSpec.secondaryDim()}onSecondary(){return r.colorSpec.onSecondary()}secondaryContainer(){return r.colorSpec.secondaryContainer()}onSecondaryContainer(){return r.colorSpec.onSecondaryContainer()}secondaryFixed(){return r.colorSpec.secondaryFixed()}secondaryFixedDim(){return r.colorSpec.secondaryFixedDim()}onSecondaryFixed(){return r.colorSpec.onSecondaryFixed()}onSecondaryFixedVariant(){return r.colorSpec.onSecondaryFixedVariant()}tertiary(){return r.colorSpec.tertiary()}tertiaryDim(){return r.colorSpec.tertiaryDim()}onTertiary(){return r.colorSpec.onTertiary()}tertiaryContainer(){return r.colorSpec.tertiaryContainer()}onTertiaryContainer(){return r.colorSpec.onTertiaryContainer()}tertiaryFixed(){return r.colorSpec.tertiaryFixed()}tertiaryFixedDim(){return r.colorSpec.tertiaryFixedDim()}onTertiaryFixed(){return r.colorSpec.onTertiaryFixed()}onTertiaryFixedVariant(){return r.colorSpec.onTertiaryFixedVariant()}error(){return r.colorSpec.error()}errorDim(){return r.colorSpec.errorDim()}onError(){return r.colorSpec.onError()}errorContainer(){return r.colorSpec.errorContainer()}onErrorContainer(){return r.colorSpec.onErrorContainer()}static highestSurface(t){return r.colorSpec.highestSurface(t)}};h.contentAccentToneDelta=15;h.colorSpec=new Et;h.primaryPaletteKeyColor=h.colorSpec.primaryPaletteKeyColor();h.secondaryPaletteKeyColor=h.colorSpec.secondaryPaletteKeyColor();h.tertiaryPaletteKeyColor=h.colorSpec.tertiaryPaletteKeyColor();h.neutralPaletteKeyColor=h.colorSpec.neutralPaletteKeyColor();h.neutralVariantPaletteKeyColor=h.colorSpec.neutralVariantPaletteKeyColor();h.background=h.colorSpec.background();h.onBackground=h.colorSpec.onBackground();h.surface=h.colorSpec.surface();h.surfaceDim=h.colorSpec.surfaceDim();h.surfaceBright=h.colorSpec.surfaceBright();h.surfaceContainerLowest=h.colorSpec.surfaceContainerLowest();h.surfaceContainerLow=h.colorSpec.surfaceContainerLow();h.surfaceContainer=h.colorSpec.surfaceContainer();h.surfaceContainerHigh=h.colorSpec.surfaceContainerHigh();h.surfaceContainerHighest=h.colorSpec.surfaceContainerHighest();h.onSurface=h.colorSpec.onSurface();h.surfaceVariant=h.colorSpec.surfaceVariant();h.onSurfaceVariant=h.colorSpec.onSurfaceVariant();h.inverseSurface=h.colorSpec.inverseSurface();h.inverseOnSurface=h.colorSpec.inverseOnSurface();h.outline=h.colorSpec.outline();h.outlineVariant=h.colorSpec.outlineVariant();h.shadow=h.colorSpec.shadow();h.scrim=h.colorSpec.scrim();h.surfaceTint=h.colorSpec.surfaceTint();h.primary=h.colorSpec.primary();h.onPrimary=h.colorSpec.onPrimary();h.primaryContainer=h.colorSpec.primaryContainer();h.onPrimaryContainer=h.colorSpec.onPrimaryContainer();h.inversePrimary=h.colorSpec.inversePrimary();h.secondary=h.colorSpec.secondary();h.onSecondary=h.colorSpec.onSecondary();h.secondaryContainer=h.colorSpec.secondaryContainer();h.onSecondaryContainer=h.colorSpec.onSecondaryContainer();h.tertiary=h.colorSpec.tertiary();h.onTertiary=h.colorSpec.onTertiary();h.tertiaryContainer=h.colorSpec.tertiaryContainer();h.onTertiaryContainer=h.colorSpec.onTertiaryContainer();h.error=h.colorSpec.error();h.onError=h.colorSpec.onError();h.errorContainer=h.colorSpec.errorContainer();h.onErrorContainer=h.colorSpec.onErrorContainer();h.primaryFixed=h.colorSpec.primaryFixed();h.primaryFixedDim=h.colorSpec.primaryFixedDim();h.onPrimaryFixed=h.colorSpec.onPrimaryFixed();h.onPrimaryFixedVariant=h.colorSpec.onPrimaryFixedVariant();h.secondaryFixed=h.colorSpec.secondaryFixed();h.secondaryFixedDim=h.colorSpec.secondaryFixedDim();h.onSecondaryFixed=h.colorSpec.onSecondaryFixed();h.onSecondaryFixedVariant=h.colorSpec.onSecondaryFixedVariant();h.tertiaryFixed=h.colorSpec.tertiaryFixed();h.tertiaryFixedDim=h.colorSpec.tertiaryFixedDim();h.onTertiaryFixed=h.colorSpec.onTertiaryFixed();h.onTertiaryFixedVariant=h.colorSpec.onTertiaryFixedVariant();/**
 * @license
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var F=class r{static maybeFallbackSpecVersion(t,e){switch(e){case s.EXPRESSIVE:case s.VIBRANT:case s.TONAL_SPOT:case s.NEUTRAL:return t;default:return"2021"}}constructor(t){this.sourceColorArgb=t.sourceColorHct.toInt(),this.variant=t.variant,this.contrastLevel=t.contrastLevel,this.isDark=t.isDark,this.platform=t.platform??"phone",this.specVersion=r.maybeFallbackSpecVersion(t.specVersion??"2021",this.variant),this.sourceColorHct=t.sourceColorHct,this.primaryPalette=t.primaryPalette??gt(this.specVersion).getPrimaryPalette(this.variant,t.sourceColorHct,this.isDark,this.platform,this.contrastLevel),this.secondaryPalette=t.secondaryPalette??gt(this.specVersion).getSecondaryPalette(this.variant,t.sourceColorHct,this.isDark,this.platform,this.contrastLevel),this.tertiaryPalette=t.tertiaryPalette??gt(this.specVersion).getTertiaryPalette(this.variant,t.sourceColorHct,this.isDark,this.platform,this.contrastLevel),this.neutralPalette=t.neutralPalette??gt(this.specVersion).getNeutralPalette(this.variant,t.sourceColorHct,this.isDark,this.platform,this.contrastLevel),this.neutralVariantPalette=t.neutralVariantPalette??gt(this.specVersion).getNeutralVariantPalette(this.variant,t.sourceColorHct,this.isDark,this.platform,this.contrastLevel),this.errorPalette=t.errorPalette??gt(this.specVersion).getErrorPalette(this.variant,t.sourceColorHct,this.isDark,this.platform,this.contrastLevel)??x.fromHueAndChroma(25,84),this.colors=new h}toString(){return`Scheme: variant=${s[this.variant]}, mode=${this.isDark?"dark":"light"}, platform=${this.platform}, contrastLevel=${this.contrastLevel.toFixed(1)}, seed=${this.sourceColorHct.toString()}, specVersion=${this.specVersion}`}static getPiecewiseHue(t,e,n){let a=Math.min(e.length-1,n.length),o=t.hue;for(let i=0;i<a;i++)if(o>=e[i]&&o<e[i+1])return z(n[i]);return o}static getRotatedHue(t,e,n){let a=r.getPiecewiseHue(t,e,n);return Math.min(e.length-1,n.length)<=0&&(a=0),z(t.hue+a)}getArgb(t){return t.getArgb(this)}getHct(t){return t.getHct(this)}get primaryPaletteKeyColor(){return this.getArgb(this.colors.primaryPaletteKeyColor())}get secondaryPaletteKeyColor(){return this.getArgb(this.colors.secondaryPaletteKeyColor())}get tertiaryPaletteKeyColor(){return this.getArgb(this.colors.tertiaryPaletteKeyColor())}get neutralPaletteKeyColor(){return this.getArgb(this.colors.neutralPaletteKeyColor())}get neutralVariantPaletteKeyColor(){return this.getArgb(this.colors.neutralVariantPaletteKeyColor())}get errorPaletteKeyColor(){return this.getArgb(this.colors.errorPaletteKeyColor())}get background(){return this.getArgb(this.colors.background())}get onBackground(){return this.getArgb(this.colors.onBackground())}get surface(){return this.getArgb(this.colors.surface())}get surfaceDim(){return this.getArgb(this.colors.surfaceDim())}get surfaceBright(){return this.getArgb(this.colors.surfaceBright())}get surfaceContainerLowest(){return this.getArgb(this.colors.surfaceContainerLowest())}get surfaceContainerLow(){return this.getArgb(this.colors.surfaceContainerLow())}get surfaceContainer(){return this.getArgb(this.colors.surfaceContainer())}get surfaceContainerHigh(){return this.getArgb(this.colors.surfaceContainerHigh())}get surfaceContainerHighest(){return this.getArgb(this.colors.surfaceContainerHighest())}get onSurface(){return this.getArgb(this.colors.onSurface())}get surfaceVariant(){return this.getArgb(this.colors.surfaceVariant())}get onSurfaceVariant(){return this.getArgb(this.colors.onSurfaceVariant())}get inverseSurface(){return this.getArgb(this.colors.inverseSurface())}get inverseOnSurface(){return this.getArgb(this.colors.inverseOnSurface())}get outline(){return this.getArgb(this.colors.outline())}get outlineVariant(){return this.getArgb(this.colors.outlineVariant())}get shadow(){return this.getArgb(this.colors.shadow())}get scrim(){return this.getArgb(this.colors.scrim())}get surfaceTint(){return this.getArgb(this.colors.surfaceTint())}get primary(){return this.getArgb(this.colors.primary())}get primaryDim(){let t=this.colors.primaryDim();if(t===void 0)throw new Error("`primaryDim` color is undefined prior to 2025 spec.");return this.getArgb(t)}get onPrimary(){return this.getArgb(this.colors.onPrimary())}get primaryContainer(){return this.getArgb(this.colors.primaryContainer())}get onPrimaryContainer(){return this.getArgb(this.colors.onPrimaryContainer())}get primaryFixed(){return this.getArgb(this.colors.primaryFixed())}get primaryFixedDim(){return this.getArgb(this.colors.primaryFixedDim())}get onPrimaryFixed(){return this.getArgb(this.colors.onPrimaryFixed())}get onPrimaryFixedVariant(){return this.getArgb(this.colors.onPrimaryFixedVariant())}get inversePrimary(){return this.getArgb(this.colors.inversePrimary())}get secondary(){return this.getArgb(this.colors.secondary())}get secondaryDim(){let t=this.colors.secondaryDim();if(t===void 0)throw new Error("`secondaryDim` color is undefined prior to 2025 spec.");return this.getArgb(t)}get onSecondary(){return this.getArgb(this.colors.onSecondary())}get secondaryContainer(){return this.getArgb(this.colors.secondaryContainer())}get onSecondaryContainer(){return this.getArgb(this.colors.onSecondaryContainer())}get secondaryFixed(){return this.getArgb(this.colors.secondaryFixed())}get secondaryFixedDim(){return this.getArgb(this.colors.secondaryFixedDim())}get onSecondaryFixed(){return this.getArgb(this.colors.onSecondaryFixed())}get onSecondaryFixedVariant(){return this.getArgb(this.colors.onSecondaryFixedVariant())}get tertiary(){return this.getArgb(this.colors.tertiary())}get tertiaryDim(){let t=this.colors.tertiaryDim();if(t===void 0)throw new Error("`tertiaryDim` color is undefined prior to 2025 spec.");return this.getArgb(t)}get onTertiary(){return this.getArgb(this.colors.onTertiary())}get tertiaryContainer(){return this.getArgb(this.colors.tertiaryContainer())}get onTertiaryContainer(){return this.getArgb(this.colors.onTertiaryContainer())}get tertiaryFixed(){return this.getArgb(this.colors.tertiaryFixed())}get tertiaryFixedDim(){return this.getArgb(this.colors.tertiaryFixedDim())}get onTertiaryFixed(){return this.getArgb(this.colors.onTertiaryFixed())}get onTertiaryFixedVariant(){return this.getArgb(this.colors.onTertiaryFixedVariant())}get error(){return this.getArgb(this.colors.error())}get errorDim(){let t=this.colors.errorDim();if(t===void 0)throw new Error("`errorDim` color is undefined prior to 2025 spec.");return this.getArgb(t)}get onError(){return this.getArgb(this.colors.onError())}get errorContainer(){return this.getArgb(this.colors.errorContainer())}get onErrorContainer(){return this.getArgb(this.colors.onErrorContainer())}};F.DEFAULT_SPEC_VERSION="2021";F.DEFAULT_PLATFORM="phone";var It=class{getPrimaryPalette(t,e,n,a,o){switch(t){case s.CONTENT:case s.FIDELITY:return x.fromHueAndChroma(e.hue,e.chroma);case s.FRUIT_SALAD:return x.fromHueAndChroma(z(e.hue-50),48);case s.MONOCHROME:return x.fromHueAndChroma(e.hue,0);case s.NEUTRAL:return x.fromHueAndChroma(e.hue,12);case s.RAINBOW:return x.fromHueAndChroma(e.hue,48);case s.TONAL_SPOT:return x.fromHueAndChroma(e.hue,36);case s.EXPRESSIVE:return x.fromHueAndChroma(z(e.hue+240),40);case s.VIBRANT:return x.fromHueAndChroma(e.hue,200);default:throw new Error(`Unsupported variant: ${t}`)}}getSecondaryPalette(t,e,n,a,o){switch(t){case s.CONTENT:case s.FIDELITY:return x.fromHueAndChroma(e.hue,Math.max(e.chroma-32,e.chroma*.5));case s.FRUIT_SALAD:return x.fromHueAndChroma(z(e.hue-50),36);case s.MONOCHROME:return x.fromHueAndChroma(e.hue,0);case s.NEUTRAL:return x.fromHueAndChroma(e.hue,8);case s.RAINBOW:return x.fromHueAndChroma(e.hue,16);case s.TONAL_SPOT:return x.fromHueAndChroma(e.hue,16);case s.EXPRESSIVE:return x.fromHueAndChroma(F.getRotatedHue(e,[0,21,51,121,151,191,271,321,360],[45,95,45,20,45,90,45,45,45]),24);case s.VIBRANT:return x.fromHueAndChroma(F.getRotatedHue(e,[0,41,61,101,131,181,251,301,360],[18,15,10,12,15,18,15,12,12]),24);default:throw new Error(`Unsupported variant: ${t}`)}}getTertiaryPalette(t,e,n,a,o){switch(t){case s.CONTENT:return x.fromHct(ut.fixIfDisliked(new St(e).analogous(3,6)[2]));case s.FIDELITY:return x.fromHct(ut.fixIfDisliked(new St(e).complement));case s.FRUIT_SALAD:return x.fromHueAndChroma(e.hue,36);case s.MONOCHROME:return x.fromHueAndChroma(e.hue,0);case s.NEUTRAL:return x.fromHueAndChroma(e.hue,16);case s.RAINBOW:case s.TONAL_SPOT:return x.fromHueAndChroma(z(e.hue+60),24);case s.EXPRESSIVE:return x.fromHueAndChroma(F.getRotatedHue(e,[0,21,51,121,151,191,271,321,360],[120,120,20,45,20,15,20,120,120]),32);case s.VIBRANT:return x.fromHueAndChroma(F.getRotatedHue(e,[0,41,61,101,131,181,251,301,360],[35,30,20,25,30,35,30,25,25]),32);default:throw new Error(`Unsupported variant: ${t}`)}}getNeutralPalette(t,e,n,a,o){switch(t){case s.CONTENT:case s.FIDELITY:return x.fromHueAndChroma(e.hue,e.chroma/8);case s.FRUIT_SALAD:return x.fromHueAndChroma(e.hue,10);case s.MONOCHROME:return x.fromHueAndChroma(e.hue,0);case s.NEUTRAL:return x.fromHueAndChroma(e.hue,2);case s.RAINBOW:return x.fromHueAndChroma(e.hue,0);case s.TONAL_SPOT:return x.fromHueAndChroma(e.hue,6);case s.EXPRESSIVE:return x.fromHueAndChroma(z(e.hue+15),8);case s.VIBRANT:return x.fromHueAndChroma(e.hue,10);default:throw new Error(`Unsupported variant: ${t}`)}}getNeutralVariantPalette(t,e,n,a,o){switch(t){case s.CONTENT:return x.fromHueAndChroma(e.hue,e.chroma/8+4);case s.FIDELITY:return x.fromHueAndChroma(e.hue,e.chroma/8+4);case s.FRUIT_SALAD:return x.fromHueAndChroma(e.hue,16);case s.MONOCHROME:return x.fromHueAndChroma(e.hue,0);case s.NEUTRAL:return x.fromHueAndChroma(e.hue,2);case s.RAINBOW:return x.fromHueAndChroma(e.hue,0);case s.TONAL_SPOT:return x.fromHueAndChroma(e.hue,8);case s.EXPRESSIVE:return x.fromHueAndChroma(z(e.hue+15),12);case s.VIBRANT:return x.fromHueAndChroma(e.hue,12);default:throw new Error(`Unsupported variant: ${t}`)}}getErrorPalette(t,e,n,a,o){}},ne=class r extends It{getPrimaryPalette(t,e,n,a,o){switch(t){case s.NEUTRAL:return x.fromHueAndChroma(e.hue,a==="phone"?T.isBlue(e.hue)?12:8:T.isBlue(e.hue)?16:12);case s.TONAL_SPOT:return x.fromHueAndChroma(e.hue,a==="phone"&&n?26:32);case s.EXPRESSIVE:return x.fromHueAndChroma(e.hue,a==="phone"?n?36:48:40);case s.VIBRANT:return x.fromHueAndChroma(e.hue,a==="phone"?74:56);default:return super.getPrimaryPalette(t,e,n,a,o)}}getSecondaryPalette(t,e,n,a,o){switch(t){case s.NEUTRAL:return x.fromHueAndChroma(e.hue,a==="phone"?T.isBlue(e.hue)?6:4:T.isBlue(e.hue)?10:6);case s.TONAL_SPOT:return x.fromHueAndChroma(e.hue,16);case s.EXPRESSIVE:return x.fromHueAndChroma(F.getRotatedHue(e,[0,105,140,204,253,278,300,333,360],[-160,155,-100,96,-96,-156,-165,-160]),a==="phone"&&n?16:24);case s.VIBRANT:return x.fromHueAndChroma(F.getRotatedHue(e,[0,38,105,140,333,360],[-14,10,-14,10,-14]),a==="phone"?56:36);default:return super.getSecondaryPalette(t,e,n,a,o)}}getTertiaryPalette(t,e,n,a,o){switch(t){case s.NEUTRAL:return x.fromHueAndChroma(F.getRotatedHue(e,[0,38,105,161,204,278,333,360],[-32,26,10,-39,24,-15,-32]),a==="phone"?20:36);case s.TONAL_SPOT:return x.fromHueAndChroma(F.getRotatedHue(e,[0,20,71,161,333,360],[-40,48,-32,40,-32]),a==="phone"?28:32);case s.EXPRESSIVE:return x.fromHueAndChroma(F.getRotatedHue(e,[0,105,140,204,253,278,300,333,360],[-165,160,-105,101,-101,-160,-170,-165]),48);case s.VIBRANT:return x.fromHueAndChroma(F.getRotatedHue(e,[0,38,71,105,140,161,253,333,360],[-72,35,24,-24,62,50,62,-72]),56);default:return super.getTertiaryPalette(t,e,n,a,o)}}static getExpressiveNeutralHue(t){return F.getRotatedHue(t,[0,71,124,253,278,300,360],[10,0,10,0,10,0])}static getExpressiveNeutralChroma(t,e,n){let a=r.getExpressiveNeutralHue(t);return n==="phone"?e?T.isYellow(a)?6:14:18:12}static getVibrantNeutralHue(t){return F.getRotatedHue(t,[0,38,105,140,333,360],[-14,10,-14,10,-14])}static getVibrantNeutralChroma(t,e){let n=r.getVibrantNeutralHue(t);return e==="phone"||T.isBlue(n)?28:20}getNeutralPalette(t,e,n,a,o){switch(t){case s.NEUTRAL:return x.fromHueAndChroma(e.hue,a==="phone"?1.4:6);case s.TONAL_SPOT:return x.fromHueAndChroma(e.hue,a==="phone"?5:10);case s.EXPRESSIVE:return x.fromHueAndChroma(r.getExpressiveNeutralHue(e),r.getExpressiveNeutralChroma(e,n,a));case s.VIBRANT:return x.fromHueAndChroma(r.getVibrantNeutralHue(e),r.getVibrantNeutralChroma(e,a));default:return super.getNeutralPalette(t,e,n,a,o)}}getNeutralVariantPalette(t,e,n,a,o){switch(t){case s.NEUTRAL:return x.fromHueAndChroma(e.hue,(a==="phone"?1.4:6)*2.2);case s.TONAL_SPOT:return x.fromHueAndChroma(e.hue,(a==="phone"?5:10)*1.7);case s.EXPRESSIVE:let i=r.getExpressiveNeutralHue(e),c=r.getExpressiveNeutralChroma(e,n,a);return x.fromHueAndChroma(i,c*(i>=105&&i<125?1.6:2.3));case s.VIBRANT:let f=r.getVibrantNeutralHue(e),g=r.getVibrantNeutralChroma(e,a);return x.fromHueAndChroma(f,g*1.29);default:return super.getNeutralVariantPalette(t,e,n,a,o)}}getErrorPalette(t,e,n,a,o){let i=F.getPiecewiseHue(e,[0,3,13,23,33,43,153,273,360],[12,22,32,12,22,32,22,12]);switch(t){case s.NEUTRAL:return x.fromHueAndChroma(i,a==="phone"?50:40);case s.TONAL_SPOT:return x.fromHueAndChroma(i,a==="phone"?60:48);case s.EXPRESSIVE:return x.fromHueAndChroma(i,a==="phone"?64:48);case s.VIBRANT:return x.fromHueAndChroma(i,a==="phone"?80:60);default:return super.getErrorPalette(t,e,n,a,o)}}},Me=new It,Be=new ne;function gt(r){return r==="2025"?Be:Me}/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *//**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var Mt=class{fromInt(t){return Ft(t)}toInt(t){return de(t[0],t[1],t[2])}distance(t,e){let n=t[0]-e[0],a=t[1]-e[1],o=t[2]-e[2];return n*n+a*a+o*o}};/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var Re=10,Le=3,Bt=class{static quantize(t,e,n){let a=new Map,o=new Array,i=new Array,c=new Mt,f=0;for(let S=0;S<t.length;S++){let k=t[S],I=a.get(k);I===void 0?(f++,o.push(c.fromInt(k)),i.push(k),a.set(k,1)):a.set(k,I+1)}let g=new Array;for(let S=0;S<f;S++){let k=i[S],I=a.get(k);I!==void 0&&(g[S]=I)}let m=Math.min(n,f);e.length>0&&(m=Math.min(m,e.length));let y=new Array;for(let S=0;S<e.length;S++)y.push(c.fromInt(e[S]));let P=m-y.length;if(e.length===0&&P>0)for(let S=0;S<P;S++){let k=Math.random()*100,I=Math.random()*201+-100,L=Math.random()*201+-100;y.push(new Array(k,I,L))}let d=new Array;for(let S=0;S<f;S++)d.push(Math.floor(Math.random()*m));let p=new Array;for(let S=0;S<m;S++){p.push(new Array);for(let k=0;k<m;k++)p[S].push(0)}let l=new Array;for(let S=0;S<m;S++){l.push(new Array);for(let k=0;k<m;k++)l[S].push(new ae)}let C=new Array;for(let S=0;S<m;S++)C.push(0);for(let S=0;S<Re;S++){for(let A=0;A<m;A++){for(let E=A+1;E<m;E++){let V=c.distance(y[A],y[E]);l[E][A].distance=V,l[E][A].index=A,l[A][E].distance=V,l[A][E].index=E}l[A].sort();for(let E=0;E<m;E++)p[A][E]=l[A][E].index}let k=0;for(let A=0;A<f;A++){let E=o[A],V=d[A],R=y[V],Y=c.distance(E,R),q=Y,tt=-1;for(let _=0;_<m;_++){if(l[V][_].distance>=4*Y)continue;let it=c.distance(E,y[_]);it<q&&(q=it,tt=_)}tt!==-1&&Math.abs(Math.sqrt(q)-Math.sqrt(Y))>Le&&(k++,d[A]=tt)}if(k===0&&S!==0)break;let I=new Array(m).fill(0),L=new Array(m).fill(0),O=new Array(m).fill(0);for(let A=0;A<m;A++)C[A]=0;for(let A=0;A<f;A++){let E=d[A],V=o[A],R=g[A];C[E]+=R,I[E]+=V[0]*R,L[E]+=V[1]*R,O[E]+=V[2]*R}for(let A=0;A<m;A++){let E=C[A];if(E===0){y[A]=[0,0,0];continue}let V=I[A]/E,R=L[A]/E,Y=O[A]/E;y[A]=[V,R,Y]}}let v=new Map;for(let S=0;S<m;S++){let k=C[S];if(k===0)continue;let I=c.toInt(y[S]);v.has(I)||v.set(I,k)}return v}},ae=class{constructor(){this.distance=-1,this.index=-1}};/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var Rt=class{static quantize(t){let e=new Map;for(let n=0;n<t.length;n++){let a=t[n];pe(a)<255||e.set(a,(e.get(a)??0)+1)}return e}};/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var Lt=5,Z=33,xt=35937,K={RED:"red",GREEN:"green",BLUE:"blue"},Ot=class{constructor(t=[],e=[],n=[],a=[],o=[],i=[]){this.weights=t,this.momentsR=e,this.momentsG=n,this.momentsB=a,this.moments=o,this.cubes=i}quantize(t,e){this.constructHistogram(t),this.computeMoments();let n=this.createBoxes(e);return this.createResult(n.resultCount)}constructHistogram(t){this.weights=Array.from({length:xt}).fill(0),this.momentsR=Array.from({length:xt}).fill(0),this.momentsG=Array.from({length:xt}).fill(0),this.momentsB=Array.from({length:xt}).fill(0),this.moments=Array.from({length:xt}).fill(0);let e=Rt.quantize(t);for(let[n,a]of e.entries()){let o=mt(n),i=ft(n),c=pt(n),f=8-Lt,g=(o>>f)+1,m=(i>>f)+1,y=(c>>f)+1,P=this.getIndex(g,m,y);this.weights[P]=(this.weights[P]??0)+a,this.momentsR[P]+=a*o,this.momentsG[P]+=a*i,this.momentsB[P]+=a*c,this.moments[P]+=a*(o*o+i*i+c*c)}}computeMoments(){for(let t=1;t<Z;t++){let e=Array.from({length:Z}).fill(0),n=Array.from({length:Z}).fill(0),a=Array.from({length:Z}).fill(0),o=Array.from({length:Z}).fill(0),i=Array.from({length:Z}).fill(0);for(let c=1;c<Z;c++){let f=0,g=0,m=0,y=0,P=0;for(let d=1;d<Z;d++){let p=this.getIndex(t,c,d);f+=this.weights[p],g+=this.momentsR[p],m+=this.momentsG[p],y+=this.momentsB[p],P+=this.moments[p],e[d]+=f,n[d]+=g,a[d]+=m,o[d]+=y,i[d]+=P;let l=this.getIndex(t-1,c,d);this.weights[p]=this.weights[l]+e[d],this.momentsR[p]=this.momentsR[l]+n[d],this.momentsG[p]=this.momentsG[l]+a[d],this.momentsB[p]=this.momentsB[l]+o[d],this.moments[p]=this.moments[l]+i[d]}}}}createBoxes(t){this.cubes=Array.from({length:t}).fill(0).map(()=>new oe);let e=Array.from({length:t}).fill(0);this.cubes[0].r0=0,this.cubes[0].g0=0,this.cubes[0].b0=0,this.cubes[0].r1=Z-1,this.cubes[0].g1=Z-1,this.cubes[0].b1=Z-1;let n=t,a=0;for(let o=1;o<t;o++){this.cut(this.cubes[a],this.cubes[o])?(e[a]=this.cubes[a].vol>1?this.variance(this.cubes[a]):0,e[o]=this.cubes[o].vol>1?this.variance(this.cubes[o]):0):(e[a]=0,o--),a=0;let i=e[0];for(let c=1;c<=o;c++)e[c]>i&&(i=e[c],a=c);if(i<=0){n=o+1;break}}return new ie(t,n)}createResult(t){let e=[];for(let n=0;n<t;++n){let a=this.cubes[n],o=this.volume(a,this.weights);if(o>0){let i=Math.round(this.volume(a,this.momentsR)/o),c=Math.round(this.volume(a,this.momentsG)/o),f=Math.round(this.volume(a,this.momentsB)/o),g=255<<24|(i&255)<<16|(c&255)<<8|f&255;e.push(g)}}return e}variance(t){let e=this.volume(t,this.momentsR),n=this.volume(t,this.momentsG),a=this.volume(t,this.momentsB),o=this.moments[this.getIndex(t.r1,t.g1,t.b1)]-this.moments[this.getIndex(t.r1,t.g1,t.b0)]-this.moments[this.getIndex(t.r1,t.g0,t.b1)]+this.moments[this.getIndex(t.r1,t.g0,t.b0)]-this.moments[this.getIndex(t.r0,t.g1,t.b1)]+this.moments[this.getIndex(t.r0,t.g1,t.b0)]+this.moments[this.getIndex(t.r0,t.g0,t.b1)]-this.moments[this.getIndex(t.r0,t.g0,t.b0)],i=e*e+n*n+a*a,c=this.volume(t,this.weights);return o-i/c}cut(t,e){let n=this.volume(t,this.momentsR),a=this.volume(t,this.momentsG),o=this.volume(t,this.momentsB),i=this.volume(t,this.weights),c=this.maximize(t,K.RED,t.r0+1,t.r1,n,a,o,i),f=this.maximize(t,K.GREEN,t.g0+1,t.g1,n,a,o,i),g=this.maximize(t,K.BLUE,t.b0+1,t.b1,n,a,o,i),m,y=c.maximum,P=f.maximum,d=g.maximum;if(y>=P&&y>=d){if(c.cutLocation<0)return!1;m=K.RED}else P>=y&&P>=d?m=K.GREEN:m=K.BLUE;switch(e.r1=t.r1,e.g1=t.g1,e.b1=t.b1,m){case K.RED:t.r1=c.cutLocation,e.r0=t.r1,e.g0=t.g0,e.b0=t.b0;break;case K.GREEN:t.g1=f.cutLocation,e.r0=t.r0,e.g0=t.g1,e.b0=t.b0;break;case K.BLUE:t.b1=g.cutLocation,e.r0=t.r0,e.g0=t.g0,e.b0=t.b1;break;default:throw new Error("unexpected direction "+m)}return t.vol=(t.r1-t.r0)*(t.g1-t.g0)*(t.b1-t.b0),e.vol=(e.r1-e.r0)*(e.g1-e.g0)*(e.b1-e.b0),!0}maximize(t,e,n,a,o,i,c,f){let g=this.bottom(t,e,this.momentsR),m=this.bottom(t,e,this.momentsG),y=this.bottom(t,e,this.momentsB),P=this.bottom(t,e,this.weights),d=0,p=-1,l=0,C=0,v=0,S=0;for(let k=n;k<a;k++){if(l=g+this.top(t,e,k,this.momentsR),C=m+this.top(t,e,k,this.momentsG),v=y+this.top(t,e,k,this.momentsB),S=P+this.top(t,e,k,this.weights),S===0)continue;let I=(l*l+C*C+v*v)*1,L=S*1,O=I/L;l=o-l,C=i-C,v=c-v,S=f-S,S!==0&&(I=(l*l+C*C+v*v)*1,L=S*1,O+=I/L,O>d&&(d=O,p=k))}return new se(p,d)}volume(t,e){return e[this.getIndex(t.r1,t.g1,t.b1)]-e[this.getIndex(t.r1,t.g1,t.b0)]-e[this.getIndex(t.r1,t.g0,t.b1)]+e[this.getIndex(t.r1,t.g0,t.b0)]-e[this.getIndex(t.r0,t.g1,t.b1)]+e[this.getIndex(t.r0,t.g1,t.b0)]+e[this.getIndex(t.r0,t.g0,t.b1)]-e[this.getIndex(t.r0,t.g0,t.b0)]}bottom(t,e,n){switch(e){case K.RED:return-n[this.getIndex(t.r0,t.g1,t.b1)]+n[this.getIndex(t.r0,t.g1,t.b0)]+n[this.getIndex(t.r0,t.g0,t.b1)]-n[this.getIndex(t.r0,t.g0,t.b0)];case K.GREEN:return-n[this.getIndex(t.r1,t.g0,t.b1)]+n[this.getIndex(t.r1,t.g0,t.b0)]+n[this.getIndex(t.r0,t.g0,t.b1)]-n[this.getIndex(t.r0,t.g0,t.b0)];case K.BLUE:return-n[this.getIndex(t.r1,t.g1,t.b0)]+n[this.getIndex(t.r1,t.g0,t.b0)]+n[this.getIndex(t.r0,t.g1,t.b0)]-n[this.getIndex(t.r0,t.g0,t.b0)];default:throw new Error("unexpected direction $direction")}}top(t,e,n,a){switch(e){case K.RED:return a[this.getIndex(n,t.g1,t.b1)]-a[this.getIndex(n,t.g1,t.b0)]-a[this.getIndex(n,t.g0,t.b1)]+a[this.getIndex(n,t.g0,t.b0)];case K.GREEN:return a[this.getIndex(t.r1,n,t.b1)]-a[this.getIndex(t.r1,n,t.b0)]-a[this.getIndex(t.r0,n,t.b1)]+a[this.getIndex(t.r0,n,t.b0)];case K.BLUE:return a[this.getIndex(t.r1,t.g1,n)]-a[this.getIndex(t.r1,t.g0,n)]-a[this.getIndex(t.r0,t.g1,n)]+a[this.getIndex(t.r0,t.g0,n)];default:throw new Error("unexpected direction $direction")}}getIndex(t,e,n){return(t<<Lt*2)+(t<<Lt+1)+t+(e<<Lt)+e+n}},oe=class{constructor(t=0,e=0,n=0,a=0,o=0,i=0,c=0){this.r0=t,this.r1=e,this.g0=n,this.g1=a,this.b0=o,this.b1=i,this.vol=c}},ie=class{constructor(t,e){this.requestedCount=t,this.resultCount=e}},se=class{constructor(t,e){this.cutLocation=t,this.maximum=e}};/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var At=class{static quantize(t,e){let a=new Ot().quantize(t,e);return Bt.quantize(t,a,e)}};/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *//**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *//**
 * @license
 * Copyright 2023 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var Vt=class extends F{constructor(t,e,n,a=F.DEFAULT_SPEC_VERSION,o=F.DEFAULT_PLATFORM){super({sourceColorHct:t,variant:s.CONTENT,contrastLevel:n,isDark:e,platform:o,specVersion:a})}};/**
 * @license
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var Nt=class extends F{constructor(t,e,n,a=F.DEFAULT_SPEC_VERSION,o=F.DEFAULT_PLATFORM){super({sourceColorHct:t,variant:s.EXPRESSIVE,contrastLevel:n,isDark:e,platform:o,specVersion:a})}};/**
 * @license
 * Copyright 2023 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var Ht=class extends F{constructor(t,e,n,a=F.DEFAULT_SPEC_VERSION,o=F.DEFAULT_PLATFORM){super({sourceColorHct:t,variant:s.FIDELITY,contrastLevel:n,isDark:e,platform:o,specVersion:a})}};/**
 * @license
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var Ut=class extends F{constructor(t,e,n,a=F.DEFAULT_SPEC_VERSION,o=F.DEFAULT_PLATFORM){super({sourceColorHct:t,variant:s.FRUIT_SALAD,contrastLevel:n,isDark:e,platform:o,specVersion:a})}};/**
 * @license
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var _t=class extends F{constructor(t,e,n,a=F.DEFAULT_SPEC_VERSION,o=F.DEFAULT_PLATFORM){super({sourceColorHct:t,variant:s.MONOCHROME,contrastLevel:n,isDark:e,platform:o,specVersion:a})}};/**
 * @license
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var zt=class extends F{constructor(t,e,n,a=F.DEFAULT_SPEC_VERSION,o=F.DEFAULT_PLATFORM){super({sourceColorHct:t,variant:s.NEUTRAL,contrastLevel:n,isDark:e,platform:o,specVersion:a})}};/**
 * @license
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var Gt=class extends F{constructor(t,e,n,a=F.DEFAULT_SPEC_VERSION,o=F.DEFAULT_PLATFORM){super({sourceColorHct:t,variant:s.RAINBOW,contrastLevel:n,isDark:e,platform:o,specVersion:a})}};/**
 * @license
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var Yt=class extends F{constructor(t,e,n,a=F.DEFAULT_SPEC_VERSION,o=F.DEFAULT_PLATFORM){super({sourceColorHct:t,variant:s.TONAL_SPOT,contrastLevel:n,isDark:e,platform:o,specVersion:a})}};/**
 * @license
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var Kt=class extends F{constructor(t,e,n,a=F.DEFAULT_SPEC_VERSION,o=F.DEFAULT_PLATFORM){super({sourceColorHct:t,variant:s.VIBRANT,contrastLevel:n,isDark:e,platform:o,specVersion:a})}};/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var Oe={desired:4,fallbackColorARGB:4282549748,filter:!0};function Ve(r,t){return r.score>t.score?-1:r.score<t.score?1:0}var Q=class r{constructor(){}static score(t,e){let{desired:n,fallbackColorARGB:a,filter:o}={...Oe,...e},i=[],c=new Array(360).fill(0),f=0;for(let[d,p]of t.entries()){let l=T.fromInt(d);i.push(l);let C=Math.floor(l.hue);c[C]+=p,f+=p}let g=new Array(360).fill(0);for(let d=0;d<360;d++){let p=c[d]/f;for(let l=d-14;l<d+16;l++){let C=lt(l);g[C]+=p}}let m=new Array;for(let d of i){let p=lt(Math.round(d.hue)),l=g[p];if(o&&(d.chroma<r.CUTOFF_CHROMA||l<=r.CUTOFF_EXCITED_PROPORTION))continue;let C=l*100*r.WEIGHT_PROPORTION,v=d.chroma<r.TARGET_CHROMA?r.WEIGHT_CHROMA_BELOW:r.WEIGHT_CHROMA_ABOVE,S=(d.chroma-r.TARGET_CHROMA)*v,k=C+S;m.push({hct:d,score:k})}m.sort(Ve);let y=[];for(let d=90;d>=15;d--){y.length=0;for(let{hct:p}of m)if(y.find(C=>Wt(p.hue,C.hue)<d)||y.push(p),y.length>=n)break;if(y.length>=n)break}let P=[];y.length===0&&P.push(a);for(let d of y)P.push(d.toInt());return P}};Q.TARGET_CHROMA=48;Q.WEIGHT_PROPORTION=.7;Q.WEIGHT_CHROMA_ABOVE=.3;Q.WEIGHT_CHROMA_BELOW=.1;Q.CUTOFF_CHROMA=5;Q.CUTOFF_EXCITED_PROPORTION=.01;/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function ce(r){let t=mt(r),e=ft(r),n=pt(r),a=[t.toString(16),e.toString(16),n.toString(16)];for(let[o,i]of a.entries())i.length===1&&(a[o]="0"+i);return"#"+a.join("")}function xe(r){r=r.replace("#","");let t=r.length===3,e=r.length===6,n=r.length===8;if(!t&&!e&&!n)throw new Error("unexpected hex "+r);let a=0,o=0,i=0;return t?(a=nt(r.slice(0,1).repeat(2)),o=nt(r.slice(1,2).repeat(2)),i=nt(r.slice(2,3).repeat(2))):e?(a=nt(r.slice(0,2)),o=nt(r.slice(2,4)),i=nt(r.slice(4,6))):n&&(a=nt(r.slice(2,4)),o=nt(r.slice(4,6)),i=nt(r.slice(6,8))),(255<<24|(a&255)<<16|(o&255)<<8|i&255)>>>0}function nt(r){return parseInt(r,16)}/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *//**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *//**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */window.MaterialColors=Object.freeze({Hct:T,argbFromHex:xe,argbFromRgb:ht,hexFromArgb:ce,QuantizerCelebi:At,Score:Q,TonalPalette:x,variants:Object.freeze({"tonal-spot":Yt,expressive:Nt,fidelity:Ht,content:Vt,monochrome:_t,neutral:zt,vibrant:Kt,rainbow:Gt,"fruit-salad":Ut})});})();
"use strict";

// Klaude Expressive: independent browser adaptation of Material tonal roles.
// Color mathematics belongs to the locally bundled Google library (Apache-2.0).
window.KlaudeColors ??= (() => {
  const m = window.MaterialColors;
  const seeds = Object.freeze({ slate: '#777777', lavender: '#65558f', sage: '#43664e',
    peach: '#8b4e33', ocean: '#235d91', rose: '#914468', teal: '#006a68', amber: '#795900',
    crimson: '#98415a', coral: '#9c4430', violet: '#7b4397', indigo: '#515b96',
    emerald: '#006c48', lime: '#516523', sky: '#006780', cocoa: '#80543e' });
  const roles = ['primary', 'onPrimary', 'primaryContainer', 'onPrimaryContainer',
    'secondary', 'onSecondary', 'secondaryContainer', 'onSecondaryContainer',
    'tertiary', 'onTertiary', 'tertiaryContainer', 'onTertiaryContainer',
    'background', 'onBackground', 'surface', 'onSurface', 'surfaceDim', 'surfaceBright',
    'surfaceContainerLowest', 'surfaceContainerLow', 'surfaceContainer',
    'surfaceContainerHigh', 'surfaceContainerHighest', 'surfaceVariant', 'onSurfaceVariant',
    'outline', 'outlineVariant', 'inverseSurface', 'inverseOnSurface', 'inversePrimary',
    'error', 'onError', 'errorContainer', 'onErrorContainer', 'shadow', 'scrim', 'surfaceTint'];
  const cache = new Map();
  const kebab = name => name.replace(/[A-Z]/g, match => '-' + match.toLowerCase());
  function palette(value, dark) {
    const source = value.colorSource || 'preset';
    const seed = source === 'preset' ? seeds[value.palette] : value.accent;
    const variant = source === 'preset' && value.palette === 'slate' ? 'monochrome' : value.variant;
    const key = `${seed}/${variant}/${dark}`;
    if (cache.has(key)) return cache.get(key);
    const scheme = new (m.variants[variant] || m.variants['tonal-spot'])(
      m.Hct.fromInt(m.argbFromHex(seed || seeds.lavender)), dark, 0);
    const result = Object.fromEntries(roles.map(role => [kebab(role), m.hexFromArgb(scheme[role])]));
    // Success is a separate semantic palette, never a replacement for primary.
    const success = m.TonalPalette.fromHueAndChroma(150, 35);
    for (const [role, tone] of Object.entries(dark ?
      { success: 80, 'on-success': 20, 'success-container': 30, 'on-success-container': 90 } :
      { success: 40, 'on-success': 100, 'success-container': 90, 'on-success-container': 10 }))
      result[role] = m.hexFromArgb(success.tone(tone));
    if (cache.size >= 40) cache.delete(cache.keys().next().value);
    cache.set(key, result);
    return result;
  }
  function apply(value) {
    const dark = value.theme === 'dark' || value.theme === 'system' && matchMedia('(prefers-color-scheme: dark)').matches;
    const root = document.documentElement, colors = palette(value, dark);
    for (const [role, color] of Object.entries(colors)) root.style.setProperty('--' + role, color);
    // Existing components keep their established role aliases.
    for (const [alias, role] of Object.entries({ muted: 'on-surface-variant',
      'surface-raised': 'surface-container-low', 'surface-high': 'surface-container-high' }))
      root.style.setProperty('--' + alias, colors[role]);
    root.style.setProperty('--surface-opacity', `${100 - (value.transparency || 0)}%`);
    root.style.colorScheme = dark ? 'dark' : 'light';
    root.dataset.colorSource = value.colorSource || 'preset';
    return colors;
  }
  async function fromImage(file) {
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 16 * 1024 * 1024)
      throw new Error('Choose a PNG, JPEG or WebP image up to 16 MiB.');
    // Decoding/downsampling and quantization remain on this device. Never upload.
    const image = await createImageBitmap(file, { resizeWidth: 96, resizeHeight: 96, resizeQuality: 'low' });
    try {
      const canvas = document.createElement('canvas'); canvas.width = canvas.height = 96;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      context.drawImage(image, 0, 0, 96, 96);
      const data = context.getImageData(0, 0, 96, 96).data, pixels = [];
      for (let index = 0; index < data.length; index += 4)
        if (data[index + 3] >= 128) pixels.push(m.argbFromRgb(data[index], data[index + 1], data[index + 2]));
      if (!pixels.length) throw new Error('This image has no visible colors.');
      return m.hexFromArgb(m.Score.score(m.QuantizerCelebi.quantize(pixels, 64))[0]);
    } finally { image.close(); }
  }
  return Object.freeze({ seeds, palette, apply, fromImage });
})();
/* END EARLY MATERIAL COLORS */

/* BEGIN EARLY MATERIAL GEOMETRY: python3 scripts/bundle_webui_loading.py */
/* Generated from Google Material / AndroidX; Apache-2.0.
 * Copyright 2024 The Android Open Source Project.
 * See material-loading-LICENSE.txt, material-loading-NOTICE.txt.
 * Regenerate: python3 scripts/vendor_webui_loading.py */
"use strict";
window.MaterialLoadingGeometry = Object.freeze({"names":["soft-burst","cookie-9","pentagon","pill","sunny","cookie-4","oval"],"morphs":[{"start":[-0.69740677,-0.42222887,-0.64737344,-0.4345659,-0.6135895,-0.4812628,-0.6175241,-0.5326443,-0.6183981,-0.5440564,-0.61927193,-0.55546844,-0.6201458,-0.56688064,-0.6239332,-0.6163392,-0.6277206,-0.66579795,-0.631508,-0.7152566,-0.6374899,-0.79337335,-0.5592004,-0.850495,-0.48663598,-0.82095814,-0.44049448,-0.8021765,-0.394353,-0.78339493,-0.34821153,-0.76461333,-0.33748567,-0.76024747,-0.32675982,-0.75588155,-0.31603396,-0.7515156,-0.26830465,-0.73208773,-0.21352524,-0.7500086,-0.18650717,-0.7938897,-0.18050629,-0.803636,-0.1745054,-0.8133823,-0.16850452,-0.82312864,-0.14249748,-0.86536765,-0.116490416,-0.9076067,-0.09048343,-0.9498458,-0.049406946,-1.0165597,0.047505856,-1.0167546,0.08885026,-0.95020646,0.11513979,-0.9078908,0.14142932,-0.86557513,0.16771886,-0.8232595,0.17383017,-0.8134227,0.17994149,-0.8035859,0.1860528,-0.7937491,0.2132473,-0.749977,0.26809835,-0.7322767,0.31574917,-0.7518964,0.32633248,-0.75625396,0.3369158,-0.7606115,0.34749913,-0.7649691,0.393367,-0.7838547,0.43923485,-0.80274045,0.48510265,-0.8216262,0.5575478,-0.85145473,0.63606644,-0.7946485,0.63039875,-0.71650827,0.62679493,-0.6668209,0.62319094,-0.61713356,0.61958706,-0.5674462,0.6187494,-0.5558965,0.6179117,-0.5443469,0.617074,-0.5327973,0.6133461,-0.48140043,0.64731765,-0.43483984,0.6974001,-0.42270416,0.70852333,-0.42000884,0.71964663,-0.41731352,0.73076993,-0.4146182,0.77897865,-0.40293655,0.8271874,-0.3912549,0.875396,-0.3795733,0.9515383,-0.36112309,0.98167133,-0.26901364,0.9311564,-0.2091282,0.8990353,-0.17104876,0.8669144,-0.13296926,0.8347933,-0.094889775,0.8273268,-0.08603818,0.8198602,-0.077186584,0.81239367,-0.068335,0.7791674,-0.028945327,0.7792835,0.028690815,0.81266785,0.06794667,0.8200827,0.076665536,0.82749754,0.08538441,0.8349125,0.09410327,0.8670476,0.1318901,0.8991828,0.16967691,0.93131804,0.20746374,0.9820733,0.2671454,0.95231104,0.35937524,0.8762438,0.37813163,0.8278748,0.39005822,0.77950585,0.40198487,0.7311369,0.41391158,0.71989346,0.41668397,0.70865,0.41945642,0.69740653,0.4222288,0.64737344,0.43456602,0.6135895,0.48126268,0.61752415,0.53264403,0.618398,0.5440561,0.6192719,0.55546814,0.6201458,0.5668802,0.6239331,0.616339,0.6277205,0.6657978,0.6315079,0.7152567,0.6374898,0.79337335,0.5592003,0.8504951,0.48663592,0.82095814,0.42976856,0.79781055,0.3729012,0.7746632,0.31603384,0.7515156,0.2683046,0.7320876,0.21352506,0.7500086,0.18650699,0.79388976,0.15449905,0.845875,0.12249112,0.8978605,0.09048319,0.9498458,0.074631095,0.9755918,0.050463177,0.991431,0.024382478,0.99735045,-0.017117932,1.0067699,-0.06346154,0.9910725,-0.08885044,0.9502063,-0.121251225,0.8980539,-0.15365207,0.8459017,-0.18605286,0.7937491,-0.21324718,0.7499771,-0.26809835,0.7322767,-0.31574917,0.7518964,-0.32633245,0.7562539,-0.33691573,0.7606114,-0.34749907,0.76496905,-0.39336693,0.7838547,-0.43923473,0.8027406,-0.48510265,0.8216262,-0.55754757,0.85145473,-0.6360663,0.79464865,-0.63039875,0.7165084,-0.6267949,0.66682136,-0.62319106,0.61713433,-0.6195872,0.5674473,-0.6187495,0.55589724,-0.6179117,0.54434717,-0.617074,0.5327971,-0.61334616,0.4814005,-0.64731765,0.43483996,-0.6974001,0.42270422,-0.708524,0.42000872,-0.7196478,0.41731322,-0.7307717,0.41461772,-0.7789799,0.40293616,-0.8271881,0.39125478,-0.87539625,0.37957335,-0.9515383,0.36112309,-0.9816714,0.26901364,-0.93115646,0.20912814,-0.8990356,0.17104888,-0.86691463,0.13296945,-0.8347938,0.094890125,-0.8273271,0.08603835,-0.81986034,0.077186584,-0.81239367,0.06833482,-0.7791675,0.028945208,-0.7792834,-0.028691173,-0.8126678,-0.06794685,-0.8200824,-0.07666552,-0.8274971,-0.0853842,-0.83491176,-0.094102874,-0.8670471,-0.13188991,-0.8991825,-0.1696769,-0.9313178,-0.20746398,-0.9820732,-0.26714575,-0.9523108,-0.3593756,-0.8762436,-0.37813193,-0.8278751,-0.39005852,-0.7795066,-0.40198505,-0.73113805,-0.41391152,-0.71989435,-0.416684,-0.7086505,-0.41945642,-0.69740677,-0.42222887],"end":[-0.8435092,-0.387688,-0.80134153,-0.42836124,-0.77148855,-0.48013556,-0.75741386,-0.5370116,-0.75476277,-0.54772496,-0.7526715,-0.55861926,-0.7511631,-0.56965446,-0.7453722,-0.6120212,-0.7312546,-0.6513693,-0.71062404,-0.68617654,-0.67461985,-0.74692225,-0.61877954,-0.793838,-0.55274487,-0.8188336,-0.51477635,-0.8332056,-0.47343764,-0.8403306,-0.43056142,-0.8386709,-0.41930935,-0.8382353,-0.40809566,-0.83841157,-0.39696532,-0.8391833,-0.33851853,-0.84323585,-0.28236967,-0.8637082,-0.23502842,-0.89823097,-0.22611119,-0.9047337,-0.21750645,-0.91173494,-0.20925772,-0.9192189,-0.17758882,-0.94795144,-0.14148161,-0.9690192,-0.10330403,-0.98242223,-0.036676224,-1.0058131,0.03625738,-1.0058591,0.10290999,-0.9825602,0.14123316,-0.969164,0.1774799,-0.94805026,0.20925772,-0.91921896,0.21759762,-0.9116523,0.22630128,-0.9045792,0.23532388,-0.8980159,0.28270173,-0.86355156,0.33887374,-0.84314257,0.39733008,-0.8391583,0.40834072,-0.83840775,0.4194324,-0.83824,0.43056166,-0.8386708,0.47329038,-0.84032476,0.51449215,-0.8332543,0.55235314,-0.81898147,0.6184281,-0.7940726,0.6743278,-0.74722743,0.7104105,-0.68653655,0.7311572,-0.6516405,0.74535245,-0.61216706,0.75116336,-0.5696541,0.7526883,-0.55849737,0.75480914,-0.54748464,0.75750196,-0.53665733,0.77164215,-0.47980204,0.80155367,-0.428061,0.843773,-0.38743368,0.8517252,-0.37978125,0.86011416,-0.3725231,0.86891663,-0.36569935,0.9027118,-0.3395009,0.9297294,-0.30760065,0.9495582,-0.27233043,0.9841634,-0.21077701,0.9968736,-0.13895987,0.9855032,-0.06927438,0.9789654,-0.029206717,0.9644666,0.010156227,0.94159114,0.046458244,0.9355878,0.05598522,0.93013346,0.06578489,0.92523664,0.07581012,0.899523,0.12845272,0.88917816,0.18731505,0.8954052,0.24557501,0.896578,0.25654888,0.8983389,0.2675014,0.9006958,0.27838695,0.90974456,0.32017988,0.909936,0.36198407,0.9024542,0.40174887,0.88939726,0.4711448,0.8529706,0.5343293,0.79946756,0.5804024,0.7687043,0.60689336,0.73229563,0.62772727,0.6914377,0.6408322,0.6807151,0.6442714,0.6702377,0.6482724,0.6600424,0.65280455,0.60650665,0.6766028,0.56074613,0.71504444,0.52806747,0.7636767,0.5219121,0.7728371,0.51622087,0.78235906,0.51102924,0.79221284,0.49109727,0.830044,0.4643732,0.8621905,0.43308204,0.88784266,0.3966372,0.91771984,0.35399705,0.9387871,0.30867723,0.9497649,0.29220903,0.95375407,0.275387,0.9564109,0.2583798,0.957674,0.23754755,0.9592213,0.21643752,0.9586776,0.19535972,0.95593,0.17818943,0.9536917,0.16104051,0.949991,0.14408058,0.9447668,0.13524559,0.94204533,0.12646188,0.9389105,0.11775315,0.9353535,0.10391441,0.9297013,0.089770444,0.92508537,0.07543319,0.92150587,0.0599008,0.91762805,0.04414155,0.9149664,0.02829774,0.91352123,-0.010099797,0.9100187,-0.048993945,0.91366017,-0.086359,0.9244456,-0.096962444,0.9275062,-0.10744275,0.9311422,-0.117753625,0.9353535,-0.15733975,0.9515218,-0.19847502,0.95896953,-0.23893425,0.95850676,-0.3095441,0.95769906,-0.37809503,0.93279755,-0.43275928,0.8881072,-0.46418953,0.8624115,-0.49102902,0.83017397,-0.51102954,0.7922127,-0.51627845,0.78225017,-0.5220381,0.77262676,-0.52827173,0.7633733,-0.56100476,0.71478343,-0.6068087,0.67639333,-0.6603768,0.652656,-0.6704669,0.6481849,-0.68083245,0.6442336,-0.6914381,0.64083195,-0.73215556,0.6277721,-0.7684544,0.60703623,-0.7991504,0.58067495,-0.85272145,0.5346691,-0.8892282,0.47152978,-0.90237707,0.40215737,-0.9099372,0.36227039,-0.9097755,0.32032287,-0.90069574,0.2783867,-0.8983128,0.26738077,-0.89653915,0.25630638,-0.8953664,0.24521066,-0.8892085,0.18694852,-0.89961964,0.12809832,-0.92539704,0.07548165,-0.9302527,0.06557062,-0.9356533,0.055880755,-0.94159126,0.04645765,-0.9643879,0.0102804825,-0.97886556,-0.028936574,-0.9854354,-0.06886155,-0.9969012,-0.13853899,-0.98428166,-0.21037258,-0.9497626,-0.27196681,-0.9299152,-0.30738154,-0.902828,-0.33941126,-0.86891645,-0.36569983,-0.8600167,-0.372599,-0.8515396,-0.37994218,-0.8435092,-0.387688]},{"start":[-0.20925772,-0.9192189,-0.0905422,-1.026927,0.0905422,-1.026927,0.20925772,-0.91921896,0.21688461,-0.9122993,0.22481571,-0.9057923,0.23301677,-0.8997106,0.28974292,-0.8576429,0.35938445,-0.83591574,0.43056166,-0.8386708,0.5907366,-0.844871,0.72945523,-0.72847223,0.75116336,-0.5696541,0.7608098,-0.4990799,0.7942997,-0.43426946,0.84557855,-0.38571006,0.8529922,-0.3786896,0.8607776,-0.37200877,0.86891663,-0.36569935,0.9956031,-0.26749063,1.0270481,-0.08915722,0.94159114,0.046458244,0.93610096,0.055170827,0.93106997,0.06411147,0.9265045,0.07324413,0.89492655,0.13641338,0.8856226,0.20876962,0.9006958,0.27838695,0.93461597,0.43505168,0.8440738,0.5918753,0.6914377,0.6408322,0.62361073,0.6625872,0.5656002,0.7068229,0.5266831,0.765755,0.5210567,0.77427495,0.51582944,0.7831021,0.51102924,0.79221284,0.45258254,0.9031456,0.33573383,0.96520007,0.21658653,0.9579563,0.18341671,0.9559397,0.15006875,0.9485523,0.11775315,0.9353535,0.042277336,0.9045267,-0.042277515,0.9045267,-0.117753625,0.9353535,-0.15006952,0.9485524,-0.18341778,0.95593977,-0.21658787,0.95795625,-0.3357348,0.9651996,-0.45258301,0.90314513,-0.51102954,0.7922127,-0.5158297,0.783102,-0.521057,0.7742748,-0.52668345,0.76575494,-0.5656005,0.7068226,-0.6236111,0.6625869,-0.6914381,0.64083195,-0.84407383,0.5918753,-0.93461597,0.43505168,-0.90069574,0.2783867,-0.88562244,0.20876849,-0.8949266,0.13641159,-0.92650574,0.073241554,-0.9310708,0.064109586,-0.9361015,0.05516961,-0.94159126,0.04645765,-1.0270481,-0.08915788,-0.995603,-0.2674911,-0.86891645,-0.36569983,-0.86077774,-0.372009,-0.85299253,-0.37868953,-0.8455791,-0.3857097,-0.7942999,-0.43426913,-0.76080954,-0.49907997,-0.7511631,-0.56965446,-0.72945505,-0.72847253,-0.59073645,-0.84487116,-0.43056142,-0.8386709,-0.35938418,-0.8359157,-0.28974268,-0.85764277,-0.23301661,-0.89971054,-0.22481555,-0.90579236,-0.21688446,-0.9122993,-0.20925772,-0.9192189],"end":[-0.19302462,-0.9451834,-0.07483945,-1.0182722,0.07483919,-1.0182722,0.19302432,-0.94518334,0.200771,-0.9403926,0.20838237,-0.9352879,0.2158407,-0.92986906,0.267727,-0.89217144,0.31961325,-0.8544738,0.37149948,-0.8167762,0.46833327,-0.7464224,0.56516707,-0.67606854,0.66200083,-0.60571474,0.71388704,-0.56801724,0.7657733,-0.53031975,0.8176595,-0.49262226,0.8251175,-0.48720372,0.83232415,-0.48154262,0.83927405,-0.47565582,0.9453075,-0.3858408,0.9915611,-0.24348743,0.9585705,-0.10850056,0.9564081,-0.09965258,0.9539052,-0.09083625,0.95105636,-0.08206844,0.9312376,-0.021072496,0.9114188,0.039923437,0.8916,0.100919366,0.85461295,0.21475422,0.81762576,0.32858914,0.7806386,0.44242406,0.76081985,0.50341994,0.7410011,0.5644158,0.72118235,0.62541175,0.71833366,0.6341792,0.71517664,0.64278245,0.7117256,0.65121126,0.65562135,0.7882387,0.5218112,0.8791479,0.37194443,0.8791479,0.3151638,0.8791479,0.25838315,0.8791479,0.20160255,0.87914777,0.06720087,0.8791478,-0.06720081,0.8791479,-0.20160247,0.8791479,-0.2583831,0.8791479,-0.31516367,0.8791479,-0.3719443,0.8791479,-0.5218106,0.8791479,-0.6556204,0.7882393,-0.7117249,0.65121233,-0.71517617,0.64278316,-0.71833336,0.63417953,-0.72118217,0.62541175,-0.74100095,0.5644157,-0.76081973,0.50341976,-0.7806385,0.44242376,-0.81762546,0.3285895,-0.85461247,0.2147553,-0.89159954,0.10092107,-0.91141856,0.03992457,-0.93123746,-0.02107193,-0.9510565,-0.08206844,-0.9539051,-0.09083553,-0.95640785,-0.09965112,-0.9585701,-0.108498365,-0.9915615,-0.24348547,-0.9453084,-0.3858392,-0.839275,-0.4756548,-0.83232486,-0.48154193,-0.8251178,-0.48720336,-0.8176595,-0.4926222,-0.7657732,-0.53031975,-0.7138869,-0.5680173,-0.66200066,-0.6057149,-0.56516695,-0.6760687,-0.46833318,-0.7464225,-0.37149948,-0.8167764,-0.31961328,-0.85447395,-0.26772708,-0.8921715,-0.21584088,-0.92986906,-0.20838259,-0.93528783,-0.20077126,-0.94039255,-0.19302462,-0.9451834]},{"start":[-0.21584088,-0.92986906,-0.15148938,-0.9766232,-0.07574435,-1.0000001,6.35162e-07,-0.99999994,0.028439315,-0.9999999,0.05687799,-0.99670446,0.084713645,-0.9901138,0.13101639,-0.9791504,0.1756506,-0.9590689,0.2158407,-0.92986906,0.41644704,-0.7841201,0.6170533,-0.6383711,0.8176595,-0.49262226,0.85784984,-0.46342227,0.89074147,-0.4271779,0.91547656,-0.38652894,0.93034625,-0.36209258,0.94226813,-0.3360644,0.9510562,-0.309018,0.9744628,-0.23698013,0.97563654,-0.15771829,0.95105636,-0.08206844,0.91583,0.026347373,0.8806036,0.13476315,0.8453772,0.24317896,0.81115264,0.34851158,0.77692795,0.45384425,0.7427033,0.5591769,0.73552966,0.5812552,0.728356,0.6033335,0.72118235,0.62541175,0.67202234,0.77671075,0.5310297,0.8791479,0.37194443,0.8791479,0.3016487,0.8791479,0.23135297,0.8791479,0.16105726,0.87914795,0.12827855,0.879148,0.09549986,0.87914807,0.06272114,0.879148,-0.082167365,0.879148,-0.22705585,0.8791479,-0.3719443,0.8791479,-0.5310296,0.8791479,-0.6720222,0.77671087,-0.72118217,0.62541175,-0.7659554,0.4876139,-0.81072867,0.3498162,-0.85550183,0.21201852,-0.865631,0.18084428,-0.87576014,0.14967005,-0.8858892,0.118495785,-0.90761167,0.051641062,-0.92933404,-0.015213684,-0.9510565,-0.08206844,-1.0002165,-0.2333675,-0.94636214,-0.3991142,-0.8176595,-0.4926222,-0.7988789,-0.5062671,-0.7800983,-0.51991194,-0.7613178,-0.5335568,-0.671716,-0.5986564,-0.58211416,-0.6637559,-0.49251235,-0.7288554,-0.40028852,-0.79585993,-0.30806473,-0.8628645,-0.21584088,-0.92986906],"end":[-0.11823776,-0.9061656,-0.036826503,-0.93280494,0.04892897,-0.9469642,0.13616014,-0.9474461,0.1640594,-0.9445773,0.19195843,-0.94170845,0.21985745,-0.9388397,0.26796612,-0.9338928,0.31479818,-0.9247543,0.35998437,-0.91179365,0.6262802,-0.8354122,0.83541244,-0.6262799,0.9117939,-0.35998413,0.9247545,-0.314798,0.933893,-0.26796597,0.9388399,-0.21985734,0.94170856,-0.19195819,0.9445772,-0.16405904,0.94744635,-0.13615984,0.9469644,-0.048927784,0.9328047,0.03682853,0.9061648,0.11824052,0.865834,0.24149227,0.79689896,0.35478696,0.70351505,0.4481709,0.61840034,0.5332856,0.53328586,0.61840034,0.4481709,0.70351505,0.43134442,0.72034156,0.4138715,0.73637426,0.3958104,0.7515889,0.28986162,0.84083956,0.16367185,0.9019383,0.028995197,0.92997885,-0.024946786,0.94120973,-0.08025028,0.9471374,-0.13616002,0.94744635,-0.16405928,0.9445772,-0.19195837,0.94170856,-0.21985757,0.9388399,-0.3462906,0.92583895,-0.4639064,0.883888,-0.56600183,0.81969035,-0.6684503,0.7552706,-0.75527084,0.66845,-0.81969047,0.5660015,-0.88388807,0.46390608,-0.9258388,0.34629035,-0.9388397,0.21985745,-0.9417085,0.19195819,-0.94457734,0.16405916,-0.94744617,0.1361599,-0.94713724,0.08025089,-0.9412098,0.02494812,-0.9299791,-0.028993182,-0.9019389,-0.16367106,-0.84083956,-0.28986192,-0.75158787,-0.3958114,-0.73637354,-0.41387215,-0.72034115,-0.43134472,-0.703515,-0.44817084,-0.6184002,-0.5332856,-0.5332854,-0.61840045,-0.44817066,-0.70351523,-0.35478604,-0.7968998,-0.24149047,-0.8658351,-0.11823776,-0.9061656]},{"start":[0.21985745,-0.9388397,0.22158962,-0.9386616,0.22332013,-0.93847793,0.22504899,-0.938289,0.35232812,-0.92437714,0.47054386,-0.88110685,0.5728178,-0.81535643,0.64577854,-0.7684511,0.71062624,-0.71010524,0.7648638,-0.642816,0.8039919,-0.59427214,0.8375979,-0.5410737,0.8647444,-0.48415822,0.8778515,-0.45667773,0.88945264,-0.42833075,0.89944243,-0.39922273,0.9190469,-0.34209916,0.9324453,-0.28204477,0.9388399,-0.21985734,0.9388669,-0.21959491,0.9388938,-0.21933249,0.9389208,-0.21907008,0.94176245,-0.19143333,0.94460416,-0.16379662,0.94744635,-0.13615984,0.9473612,-0.12075567,0.9468496,-0.10539752,0.94591796,-0.090101175,0.9438942,-0.05687054,0.93988854,-0.023931637,0.9339687,0.0085535515,0.9310765,0.02442415,0.92772746,0.04018646,0.92392945,0.05582159,0.9162762,0.08732699,0.9067998,0.11831601,0.8955648,0.14863412,0.8743379,0.20591581,0.84683335,0.26080263,0.8134861,0.31225237,0.78193617,0.36092925,0.7451563,0.4065296,0.70351505,0.4481709,0.6768577,0.47482818,0.6502004,0.5014855,0.6235432,0.5281428,0.591743,0.5599431,0.55994284,0.59174323,0.5281426,0.62354344,0.5014854,0.65020066,0.47482818,0.6768578,0.4481709,0.70351505,0.40652955,0.7451564,0.36092916,0.7819364,0.31225228,0.8134864,0.2608031,0.8468332,0.205917,0.8743375,0.14863612,0.8955642,0.11831778,0.9067993,0.08732854,0.91627586,0.055822894,0.92392915,0.040187642,0.9277272,0.024425212,0.9310764,0.008554492,0.9339684,-0.02393068,0.93988836,-0.05686955,0.94389415,-0.090100184,0.9459179,-0.1053969,0.9468496,-0.12075545,0.94736123,-0.13616002,0.94744635,-0.16379659,0.9446043,-0.19143301,0.94176257,-0.21906954,0.938921,-0.21933222,0.9388939,-0.2195949,0.9388669,-0.21985757,0.9388399,-0.28204453,0.93244535,-0.34209844,0.91904706,-0.39922163,0.89944273,-0.42832953,0.88945305,-0.4566765,0.87785196,-0.48415694,0.86474496,-0.5410726,0.8375986,-0.59427124,0.80399257,-0.64281535,0.7648645,-0.6877302,0.72866154,-0.7286604,0.6877313,-0.7648633,0.6428165,-0.80399144,0.5942726,-0.8375976,0.54107416,-0.864744,0.48415866,-0.87785125,0.45667782,-0.8894526,0.42833048,-0.89944243,0.39922205,-0.9190468,0.34209874,-0.93244505,0.28204465,-0.9388397,0.21985745,-0.9388667,0.21959461,-0.93889374,0.21933177,-0.93892074,0.21906893,-0.9417626,0.1914325,-0.94460434,0.16379632,-0.94744617,0.1361599,-0.94727606,0.10537601,-0.9454026,0.074775934,-0.9418784,0.0444857,-0.93428755,-0.020757489,-0.91903836,-0.08456311,-0.89665645,-0.14567137,-0.87416327,-0.2070835,-0.8444665,-0.26577133,-0.8080998,-0.32045633,-0.7777733,-0.36605865,-0.7428086,-0.4088773,-0.703515,-0.44817084,-0.6184002,-0.5332856,-0.5332854,-0.61840045,-0.44817066,-0.70351523,-0.4387483,-0.71293765,-0.42912316,-0.7221111,-0.41930562,-0.7310315,-0.32878432,-0.81327957,-0.22189946,-0.874004,-0.106665745,-0.909859,-0.04419756,-0.929296,0.02072414,-0.9414245,0.08682253,-0.94571173,0.10320262,-0.9467741,0.11965496,-0.9473549,0.13616014,-0.9474461,0.1640594,-0.9445773,0.19195843,-0.94170845,0.21985745,-0.9388397],"end":[0.3690789,-0.7718328,0.37007317,-0.77173436,0.37106907,-0.7716453,0.3720665,-0.77156574,0.45081854,-0.76528126,0.5295706,-0.7589968,0.6083224,-0.75271237,0.6853765,-0.7465634,0.7465638,-0.6853761,0.7527127,-0.60832196,0.7589971,-0.5295701,0.76528156,-0.4508183,0.7715659,-0.3720665,0.7742009,-0.33904696,0.7871852,-0.30770028,0.8086703,-0.2824887,0.8596604,-0.22265463,0.91065073,-0.16282055,0.9616409,-0.10298641,0.9618929,-0.102690734,0.96214485,-0.10239505,0.96239686,-0.10209936,0.9874656,-0.07268267,1.0,-0.036341388,1.0,-8.195639e-08,1.0,0.03634128,0.9874656,0.07268266,0.96239686,0.10209942,0.9111545,0.16222918,0.8599124,0.22235894,0.80867016,0.28248882,0.7871852,0.30770028,0.7742008,0.33904707,0.7715658,0.3720665,0.76528144,0.4508183,0.75899696,0.52957034,0.7527125,0.60832214,0.74656355,0.6853763,0.6853763,0.74656343,0.60832214,0.7527125,0.55906284,0.7566434,0.50980353,0.76057434,0.4605442,0.7645053,0.4310516,0.7668588,0.40155905,0.76921237,0.3720665,0.7715659,0.33904696,0.7742009,0.30770028,0.7871852,0.28248882,0.80867016,0.25997055,0.82786006,0.23745225,0.84704995,0.21493398,0.86623985,0.17732239,0.8982922,0.13971081,0.93034446,0.1020993,0.96239686,0.04326582,1.0125344,-0.043266,1.0125344,-0.10209942,0.96239686,-0.16222918,0.9111545,-0.22235906,0.8599124,-0.28248882,0.80867016,-0.30770028,0.7871852,-0.33904707,0.7742008,-0.3720665,0.7715658,-0.45081842,0.76528144,-0.5295703,0.75899696,-0.6083222,0.7527125,-0.6468494,0.749638,-0.6814098,0.7328039,-0.707107,0.7071066,-0.73280406,0.6814094,-0.749638,0.6468492,-0.75271255,0.60832226,-0.7527435,0.6079345,-0.7527744,0.6075466,-0.7528054,0.60715896,-0.7590589,0.52879477,-0.7653125,0.45043048,-0.77156603,0.37206626,-0.774201,0.33904684,-0.78718525,0.30770016,-0.8086703,0.28248858,-0.85991246,0.22235882,-0.9111547,0.16222906,-0.96239686,0.1020993,-1.0125344,0.04326582,-1.0125344,-0.043266058,-0.9623968,-0.10209948,-0.91115457,-0.16222918,-0.85991234,-0.22235894,-0.80867016,-0.28248876,-0.7871851,-0.30770028,-0.77420086,-0.33904696,-0.7715658,-0.37206638,-0.7653124,-0.45043048,-0.75905883,-0.5287945,-0.75280523,-0.60715854,-0.7527743,-0.6075465,-0.7527433,-0.6079345,-0.75271237,-0.6083224,-0.7496379,-0.6468493,-0.73280394,-0.6814095,-0.7071069,-0.70710665,-0.68140966,-0.732804,-0.6468493,-0.7496381,-0.60832214,-0.7527126,-0.52957016,-0.7589971,-0.45081818,-0.76528156,-0.37206626,-0.771566,-0.33904672,-0.7742009,-0.30769998,-0.78718525,-0.28248847,-0.80867034,-0.26693022,-0.821929,-0.25137195,-0.8351876,-0.23581368,-0.8484463,-0.19592574,-0.8824386,-0.15603781,-0.91643083,-0.11614987,-0.95042306,-0.11146636,-0.95441425,-0.10678286,-0.95840555,-0.10209936,-0.9623968,-0.04326594,-1.0125344,0.04326594,-1.0125344,0.10209942,-0.96239686,0.1622293,-0.91115457,0.22235906,-0.85991234,0.28248894,-0.8086701,0.2950946,-0.7979276,0.30923408,-0.78931034,0.32434955,-0.7830492,0.33855194,-0.7771664,0.35361594,-0.77336365,0.3690789,-0.7718328]},{"start":[0.96239686,-0.10209936,0.9654144,-0.09855849,0.9682503,-0.09491729,0.9709045,-0.09118784,0.99654555,-0.05516058,1.005239,-0.010897623,0.996985,0.030714195,0.9918965,0.056367062,0.9803671,0.08101237,0.96239686,0.10209942,0.9111545,0.16222918,0.8599124,0.22235894,0.80867016,0.28248882,0.7871852,0.30770028,0.7742008,0.33904707,0.7715658,0.3720665,0.76528144,0.4508183,0.75899696,0.52957034,0.7527125,0.60832214,0.74656355,0.6853763,0.6853763,0.74656343,0.60832214,0.7527125,0.55641294,0.7568549,0.5045036,0.7609973,0.4525943,0.7651397,0.43908972,0.76621735,0.4255851,0.767295,0.4120805,0.7683728,0.3987425,0.76943713,0.3854045,0.7705015,0.3720665,0.7715659,0.33904696,0.7742009,0.30770028,0.7871852,0.28248882,0.80867016,0.22235894,0.8599124,0.16222906,0.9111545,0.1020993,0.96239686,0.09855819,0.9654146,0.094916746,0.96825063,0.09118703,0.970905,0.05516013,0.9965454,0.010897867,1.0052388,-0.030713394,0.99698514,-0.05636655,0.99189675,-0.08101215,0.9803673,-0.10209942,0.96239686,-0.16222918,0.9111545,-0.22235906,0.8599124,-0.28248882,0.80867016,-0.30770028,0.7871852,-0.33904707,0.7742008,-0.3720665,0.7715658,-0.45081842,0.76528144,-0.5295703,0.75899696,-0.6083222,0.7527125,-0.6853763,0.74656355,-0.7465635,0.6853764,-0.75271255,0.60832226,-0.7568549,0.55641305,-0.7609973,0.5045038,-0.76513976,0.4525945,-0.76621747,0.43908995,-0.7672952,0.42558536,-0.76837283,0.4120808,-0.76943725,0.39874262,-0.7705016,0.38540444,-0.77156603,0.37206626,-0.774201,0.33904684,-0.78718525,0.30770016,-0.8086703,0.28248858,-0.85991246,0.22235882,-0.9111547,0.16222906,-0.96239686,0.1020993,-0.96541464,0.09855808,-0.96825075,0.09491651,-0.9709053,0.09118667,-0.9965458,0.055159446,-1.005239,0.0108967535,-0.9969848,-0.030714776,-0.9918963,-0.05636746,-0.98036695,-0.08101258,-0.9623968,-0.10209948,-0.91115457,-0.16222918,-0.85991234,-0.22235894,-0.80867016,-0.28248876,-0.7871851,-0.30770028,-0.77420086,-0.33904696,-0.7715658,-0.37206638,-0.7652814,-0.45081842,-0.7589969,-0.5295704,-0.75271237,-0.6083224,-0.7465634,-0.6853764,-0.68537617,-0.7465636,-0.60832214,-0.7527126,-0.5564126,-0.756855,-0.504503,-0.7609975,-0.45259348,-0.7651399,-0.4390892,-0.76621747,-0.4255849,-0.7672951,-0.4120807,-0.76837283,-0.39874253,-0.7694372,-0.3854044,-0.7705016,-0.37206626,-0.771566,-0.33904672,-0.7742009,-0.30769998,-0.78718525,-0.28248847,-0.80867034,-0.22235876,-0.85991246,-0.16222906,-0.9111547,-0.10209936,-0.9623968,-0.09855838,-0.9654144,-0.094917074,-0.96825045,-0.09118751,-0.97090477,-0.055160493,-0.99654543,-0.010897951,-1.005239,0.03071355,-0.9969851,0.05636665,-0.9918967,0.08101219,-0.9803673,0.10209942,-0.96239686,0.1622293,-0.91115457,0.22235906,-0.85991234,0.28248894,-0.8086701,0.3077004,-0.7871851,0.33904707,-0.77420074,0.3720665,-0.77156574,0.45081854,-0.76528126,0.5295706,-0.7589968,0.6083224,-0.75271237,0.6853765,-0.7465634,0.7465638,-0.6853761,0.7527127,-0.60832196,0.756855,-0.55641246,0.7609975,-0.504503,0.7651398,-0.45259356,0.76621747,-0.43908942,0.7672951,-0.4255853,0.7683728,-0.41208118,0.7694372,-0.39874294,0.7705015,-0.3854047,0.7715659,-0.3720665,0.7742009,-0.33904696,0.7871852,-0.30770028,0.8086703,-0.2824887,0.8599124,-0.22235894,0.9111546,-0.16222918,0.96239686,-0.10209936],"end":[0.7616068,0.14736,0.7625601,0.1496818,0.76353693,0.15199667,0.7645371,0.15430427,0.77564883,0.17994142,0.7867608,0.2055788,0.79787254,0.23121595,0.8051244,0.24794754,0.8112447,0.26469082,0.8162869,0.28139225,0.8325179,0.3351546,0.83757704,0.38848394,0.8332438,0.43959767,0.8310589,0.4653698,0.82648623,0.49057865,0.8197538,0.5149957,0.80595976,0.5650244,0.7830992,0.6117292,0.7531343,0.65314466,0.6980392,0.72929364,0.61892664,0.7875614,0.52799356,0.8157313,0.4371343,0.84387827,0.33447358,0.84197617,0.23217845,0.797838,0.20625663,0.7866535,0.18033504,0.7754688,0.15441346,0.7642844,0.13169587,0.75448227,0.10827719,0.74694496,0.084481545,0.74167216,0.047620077,0.7335042,0.009854065,0.7307704,-0.027611593,0.7334699,-0.068401925,0.73640895,-0.108836226,0.7457883,-0.1473595,0.76160663,-0.14968143,0.76256007,-0.15199639,0.76353693,-0.15430409,0.7645371,-0.17994142,0.7756491,-0.20557868,0.78676105,-0.23121595,0.7978728,-0.24794756,0.8051247,-0.26469082,0.811245,-0.28139228,0.8162872,-0.33515432,0.83251816,-0.38848335,0.8375773,-0.43959683,0.83324414,-0.46536902,0.8310593,-0.49057794,0.82648665,-0.51499504,0.81975436,-0.5650238,0.8059603,-0.6117288,0.78309983,-0.6531443,0.7531349,-0.72929347,0.69803977,-0.7875614,0.6189272,-0.81573135,0.527994,-0.84387845,0.4371346,-0.8419764,0.3344737,-0.7978381,0.23217845,-0.78665346,0.20625663,-0.7754688,0.18033504,-0.76428413,0.15441346,-0.75448203,0.13169584,-0.7469447,0.10827714,-0.741672,0.0844815,-0.73350406,0.04762019,-0.7307703,0.009854363,-0.7334697,-0.027611105,-0.73640877,-0.06840184,-0.74578834,-0.10883654,-0.761607,-0.14736018,-0.7625603,-0.14968184,-0.76353705,-0.15199654,-0.7645371,-0.15430397,-0.7756489,-0.17994136,-0.78676075,-0.20557863,-0.79787254,-0.23121595,-0.8051244,-0.24794756,-0.8112447,-0.26469082,-0.8162869,-0.28139228,-0.8325178,-0.33515432,-0.837577,-0.38848335,-0.83324385,-0.43959677,-0.83105904,-0.46536896,-0.8264864,-0.49057785,-0.81975406,-0.514995,-0.8059598,-0.5650247,-0.78309864,-0.6117304,-0.753133,-0.6531467,-0.69803756,-0.729295,-0.6189251,-0.78756225,-0.5279923,-0.8157317,-0.43713316,-0.8438784,-0.3344728,-0.84197617,-0.23217809,-0.7978381,-0.20625651,-0.7866534,-0.18033493,-0.77546877,-0.15441334,-0.76428413,-0.13169572,-0.75448203,-0.10827703,-0.74694467,-0.084481396,-0.7416719,-0.047619935,-0.73350394,-0.0098539535,-0.73077023,0.027611664,-0.7334697,0.06840223,-0.7364088,0.10883676,-0.74578834,0.14736027,-0.76160693,0.14968191,-0.76256025,0.15199661,-0.763537,0.15430403,-0.76453704,0.17994142,-0.77564883,0.2055788,-0.7867607,0.23121619,-0.79787254,0.24794781,-0.8051244,0.26469105,-0.8112447,0.2813925,-0.8162869,0.3351549,-0.83251786,0.38848424,-0.837577,0.43959802,-0.8332437,0.46537015,-0.8310588,0.49057898,-0.8264861,0.51499605,-0.8197537,0.56502473,-0.8059596,0.6117295,-0.78309894,0.653145,-0.753134,0.72929394,-0.69803876,0.7875618,-0.6189262,0.81573164,-0.52799314,0.8438785,-0.43713382,0.84197646,-0.33447307,0.7978382,-0.23217797,0.7866535,-0.20625645,0.7754688,-0.18033487,0.7642844,-0.15441334,0.7544822,-0.13169593,0.74694496,-0.10827745,0.7416723,-0.08448202,0.7335042,-0.0476203,0.7307703,-0.009854024,0.7334698,0.02761188,0.73640895,0.06840229,0.74578834,0.108836666,0.7616068,0.14736]},{"start":[0.79787254,0.23121595,0.8014275,0.239418,0.80471057,0.24762285,0.807728,0.25582418,0.9334363,0.5974985,0.598119,0.93310565,0.25623155,0.80744356,0.24821551,0.80449724,0.24019586,0.8012973,0.23217845,0.797838,0.20625663,0.7866535,0.18033504,0.7754688,0.15441346,0.7642844,0.055880666,0.7217696,-0.05584097,0.7218609,-0.15430409,0.7645371,-0.17994142,0.7756491,-0.20557868,0.78676105,-0.23121595,0.7978728,-0.29300046,0.82465166,-0.3549438,0.8360014,-0.41435513,0.8346085,-0.6398377,0.829322,-0.82884854,0.64048815,-0.8342837,0.41497043,-0.83571243,0.35568553,-0.8244547,0.2938655,-0.7978381,0.23217845,-0.78665346,0.20625663,-0.7754688,0.18033504,-0.76428413,0.15441346,-0.72176933,0.055880547,-0.7218608,-0.05584091,-0.7645371,-0.15430397,-0.7756489,-0.17994136,-0.78676075,-0.20557863,-0.79787254,-0.23121595,-0.8014275,-0.239418,-0.80471057,-0.24762285,-0.807728,-0.2558242,-0.9334363,-0.5974986,-0.59811866,-0.9331055,-0.2562312,-0.8074437,-0.24821515,-0.8044973,-0.2401955,-0.8012974,-0.23217809,-0.7978381,-0.20625651,-0.7866534,-0.18033493,-0.77546877,-0.15441334,-0.76428413,-0.055880427,-0.7217693,0.05584097,-0.72186077,0.15430403,-0.76453704,0.17994142,-0.77564883,0.2055788,-0.7867607,0.23121619,-0.79787254,0.2930007,-0.82465136,0.35494405,-0.83600104,0.41435534,-0.8346081,0.63983786,-0.82932144,0.8288488,-0.6404877,0.83428395,-0.41496992,0.83571255,-0.355685,0.8244549,-0.29386503,0.7978382,-0.23217797,0.7866535,-0.20625645,0.7754688,-0.18033487,0.7642844,-0.15441334,0.72176933,-0.055880427,0.7218609,0.055841208,0.7645371,0.15430427,0.77564883,0.17994142,0.7867608,0.2055788,0.79787254,0.23121595],"end":[0.699646,0.12829782,0.6960631,0.13470404,0.69241375,0.14110592,0.68869805,0.14750218,0.561368,0.36669397,0.36669397,0.561368,0.14750206,0.6886982,0.14126042,0.692324,0.13501343,0.6958867,0.12876227,0.6993861,0.10588863,0.7121909,0.08295907,0.724148,0.060029812,0.7352449,-0.053614713,0.7902452,-0.16725227,0.8241174,-0.2740428,0.83536047,-0.29582798,0.837654,-0.31732824,0.8390059,-0.33848548,0.83940315,-0.38779846,0.8403293,-0.43524796,0.83607006,-0.48009872,0.8264642,-0.6627528,0.7873442,-0.78734434,0.66275275,-0.8264643,0.4800985,-0.8360401,0.4353885,-0.8403026,0.38809606,-0.8394118,0.33894953,-0.8390246,0.31758475,-0.83766353,0.2958696,-0.8353417,0.27386388,-0.82407326,0.16706266,-0.79017484,0.053417765,-0.73514825,-0.06023012,-0.72415364,-0.08293749,-0.71231556,-0.10564496,-0.699646,-0.128298,-0.69606316,-0.13470414,-0.6924138,-0.14110593,-0.68869823,-0.14750212,-0.56136817,-0.36669403,-0.36669397,-0.561368,-0.14750165,-0.6886983,-0.14126,-0.6923241,-0.13501301,-0.6958868,-0.12876186,-0.69938624,-0.1058882,-0.71219105,-0.082958646,-0.72414815,-0.060029387,-0.73524505,0.05361513,-0.7902453,0.16725263,-0.82411766,0.2740431,-0.83536065,0.29582852,-0.8376542,0.31732896,-0.83900595,0.33848637,-0.83940333,0.38779908,-0.84032935,0.43524843,-0.8360701,0.48009896,-0.82646424,0.662753,-0.7873442,0.7873442,-0.662753,0.8264642,-0.48009884,0.83604014,-0.4353884,0.8403027,-0.3880956,0.83941185,-0.33894867,0.8390246,-0.31758374,0.83766353,-0.29586846,0.83534163,-0.27386257,0.8240729,-0.16706137,0.79017437,-0.053416535,0.73514754,0.060231287,0.72415316,0.082938194,0.7123153,0.10564523,0.699646,0.12829782]},{"start":[0.48009896,-0.82646424,0.48986536,-0.82437253,0.49946576,-0.8220364,0.50889605,-0.8194601,0.5546206,-0.8069685,0.596344,-0.7888305,0.63358855,-0.76552373,0.6873945,-0.73185307,0.7318529,-0.68739474,0.76552355,-0.6335887,0.78903407,-0.59601873,0.80728495,-0.5538913,0.8197862,-0.50769675,0.8222338,-0.4986521,0.82446104,-0.48945162,0.8264642,-0.48009884,0.835814,-0.4364443,0.8400984,-0.39032793,0.83946633,-0.34242767,0.83891106,-0.300344,0.83456093,-0.25688332,0.82651675,-0.21250546,0.8179873,-0.16545048,0.8053048,-0.117364265,0.7885895,-0.06879496,0.77936494,-0.041991487,0.7689122,-0.01504089,0.7572515,0.011964718,0.7443556,0.041831043,0.72998226,0.07176465,0.7141588,0.10164091,0.7060514,0.11694864,0.69756323,0.13224132,0.68869805,0.14750218,0.68473136,0.1543306,0.6806994,0.1611352,0.6766034,0.1679147,0.65945655,0.19629484,0.6411871,0.22423533,0.62189,0.25164115,0.6085646,0.27056593,0.5947493,0.28923577,0.5804751,0.3076194,0.56364673,0.3292926,0.5461807,0.350568,0.52812845,0.37139437,0.51380146,0.3879229,0.4991051,0.4041686,0.48406506,0.42010587,0.4529717,0.45305407,0.42040932,0.48468393,0.38660434,0.5147691,0.3527478,0.54490006,0.31764486,0.57348156,0.2815229,0.60028625,0.2381852,0.6324454,0.1933807,0.66204697,0.14750206,0.6886982,0.14241622,0.69165254,0.13732687,0.6945651,0.13223457,0.6974356,0.0840466,0.7245991,0.03559779,0.74800116,-0.012586162,0.7675261,-0.08023281,0.7949377,-0.14735742,0.8147076,-0.21250534,0.8265167,-0.25731114,0.83463836,-0.30118197,0.83899456,-0.34364456,0.83948123,-0.3911091,0.8400253,-0.43681413,0.8357347,-0.48009872,0.8264642,-0.48986515,0.8243725,-0.49946555,0.8220363,-0.5088958,0.81946003,-0.5546204,0.8069685,-0.5963438,0.78883046,-0.63358843,0.7655237,-0.68739486,0.7318527,-0.7318536,0.68739384,-0.7655244,0.63358724,-0.78903455,0.5960176,-0.80728525,0.55389065,-0.8197862,0.50769657,-0.8222339,0.49865192,-0.82446116,0.48945132,-0.8264643,0.4800985,-0.835814,0.4364441,-0.8400984,0.39032778,-0.83946633,0.34242746,-0.83891106,0.3003441,-0.83456093,0.25688377,-0.82651687,0.21250628,-0.81798744,0.16545084,-0.80530477,0.117364176,-0.7885892,0.06879439,-0.7793648,0.04199128,-0.76891226,0.0150410365,-0.7572518,-0.011964209,-0.7443559,-0.04183046,-0.72998273,-0.07176399,-0.71415937,-0.101640195,-0.7060518,-0.116948135,-0.6975635,-0.13224104,-0.68869823,-0.14750212,-0.68473154,-0.15433054,-0.6806996,-0.16113514,-0.6766035,-0.16791467,-0.6594567,-0.19629481,-0.6411872,-0.22423533,-0.6218901,-0.25164115,-0.60856473,-0.27056593,-0.5947494,-0.28923577,-0.5804752,-0.30761942,-0.56364673,-0.3292928,-0.54618067,-0.35056832,-0.52812815,-0.37139487,-0.51380116,-0.3879234,-0.4991048,-0.40416905,-0.4840648,-0.42010632,-0.45297146,-0.4530545,-0.42040902,-0.48468432,-0.38660404,-0.5147694,-0.35274753,-0.5449003,-0.31764457,-0.5734818,-0.28152257,-0.6002865,-0.23818487,-0.6324456,-0.1933803,-0.6620471,-0.14750165,-0.6886983,-0.14241582,-0.69165266,-0.13732643,-0.69456524,-0.13223416,-0.69743574,-0.08404617,-0.7245993,-0.03559737,-0.7480013,0.012586575,-0.76752627,0.0802332,-0.7949378,0.14735778,-0.8147077,0.21250567,-0.82651675,0.257311,-0.83463836,0.30118135,-0.83899456,0.34364352,-0.8394813,0.3911085,-0.8400255,0.43681395,-0.83573484,0.48009896,-0.82646424],"end":[0.28715208,-0.7445752,0.29678607,-0.7456373,0.30640602,-0.74804944,0.31574917,-0.7518964,0.3722005,-0.7751397,0.42865157,-0.79838294,0.48510265,-0.8216262,0.5575478,-0.85145473,0.63606644,-0.7946485,0.63039875,-0.71650827,0.62595725,-0.6552713,0.6215155,-0.5940343,0.617074,-0.5327973,0.61637294,-0.52313155,0.6170051,-0.5136368,0.6188271,-0.50451,0.6266933,-0.46510547,0.6567362,-0.4325576,0.6974001,-0.42270416,0.756732,-0.40832722,0.8160641,-0.39395022,0.875396,-0.3795733,0.9515383,-0.36112309,0.98167133,-0.26901364,0.9311564,-0.2091282,0.89156866,-0.16219717,0.8519814,-0.115266085,0.81239367,-0.068335,0.7791674,-0.028945327,0.7792835,0.028690815,0.81266785,0.06794667,0.8382998,0.09808646,0.86393166,0.12822625,0.8895637,0.15836602,0.9034817,0.17473194,0.9173999,0.19109784,0.93131804,0.20746374,0.9820733,0.2671454,0.95231104,0.35937524,0.8762438,0.37813163,0.8166313,0.3928306,0.75701904,0.4075296,0.69740653,0.4222288,0.64737344,0.43456602,0.6135895,0.48126268,0.61752415,0.53264403,0.62218523,0.5935149,0.62684655,0.6543858,0.6315079,0.7152567,0.6374898,0.79337335,0.5592003,0.8504951,0.48663592,0.82095814,0.42976856,0.79781055,0.3729012,0.7746632,0.31603384,0.7515156,0.2735352,0.7342167,0.22544691,0.7465292,0.19634408,0.7804133,0.1927622,0.7845837,0.18946789,0.78908086,0.18650699,0.79388976,0.15449905,0.845875,0.12249112,0.8978605,0.09048319,0.9498458,0.049406767,1.0165596,-0.047506034,1.0167546,-0.08885044,0.9502063,-0.121251225,0.8980539,-0.15365207,0.8459017,-0.18605286,0.7937491,-0.20791517,0.7585595,-0.24765217,0.74022,-0.28715268,0.74457526,-0.2967865,0.7456374,-0.30640623,0.7480495,-0.31574917,0.7518964,-0.37220037,0.7751396,-0.42865145,0.798383,-0.48510265,0.8216262,-0.55754757,0.85145473,-0.6360663,0.79464865,-0.63039875,0.7165084,-0.62595713,0.6552713,-0.6215156,0.5940342,-0.617074,0.5327971,-0.61637294,0.5231312,-0.6170052,0.51363635,-0.6188273,0.5045093,-0.6266938,0.46510527,-0.65673643,0.43255764,-0.6974001,0.42270422,-0.75673217,0.4083271,-0.8160642,0.39395022,-0.87539625,0.37957335,-0.9515383,0.36112309,-0.9816714,0.26901364,-0.93115646,0.20912814,-0.89156884,0.16219711,-0.8519813,0.115265846,-0.81239367,0.06833482,-0.7791675,0.028945208,-0.7792834,-0.028691173,-0.8126678,-0.06794685,-0.8382996,-0.09808655,-0.86393136,-0.12822619,-0.88956314,-0.15836586,-0.90348136,-0.17473188,-0.9173996,-0.19109793,-0.9313178,-0.20746398,-0.9820732,-0.26714575,-0.9523108,-0.3593756,-0.8762436,-0.37813193,-0.8166313,-0.39283097,-0.75701904,-0.40752995,-0.69740677,-0.42222887,-0.64737344,-0.4345659,-0.6135895,-0.4812628,-0.6175241,-0.5326443,-0.62218547,-0.59351504,-0.6268467,-0.6543858,-0.631508,-0.7152566,-0.6374899,-0.79337335,-0.5592004,-0.850495,-0.48663598,-0.82095814,-0.42976862,-0.7978106,-0.37290126,-0.77466315,-0.31603396,-0.7515156,-0.27353528,-0.7342168,-0.22544706,-0.7465292,-0.19634426,-0.78041327,-0.19276236,-0.7845837,-0.18946806,-0.7890808,-0.18650717,-0.7938897,-0.15449929,-0.8458751,-0.1224913,-0.8978604,-0.09048343,-0.9498458,-0.049406946,-1.0165597,0.047505856,-1.0167546,0.08885026,-0.95020646,0.121251106,-0.898054,0.15365195,-0.84590155,0.1860528,-0.7937491,0.20791513,-0.7585596,0.24765176,-0.7402202,0.28715208,-0.7445752]}],"shapes":{"circle":[0.99999905,-1.4901161e-08,0.99999905,0.104297325,0.98368454,0.20859468,0.9510555,0.3090167,0.8857976,0.5098598,0.75863194,0.68488824,0.5877845,0.8090161,0.41693723,0.9331441,0.21117902,0.9999989,-5.9604645e-08,0.9999988,-0.2111789,0.9999988,-0.41693723,0.93314385,-0.5877846,0.809016,-0.7586321,0.6848881,-0.88579756,0.5098598,-0.9510555,0.30901647,-1.0163134,0.10817349,-1.0163134,-0.10817367,-0.95105547,-0.30901682,-0.8857975,-0.50986016,-0.7586321,-0.6848882,-0.5877846,-0.80901605,-0.4169371,-0.93314403,-0.21117932,-0.9999988,0.0,-0.99999887,0.21117902,-0.99999887,0.41693747,-0.93314385,0.587785,-0.8090158,0.7586323,-0.68488795,0.88579786,-0.5098596,0.9510555,-0.3090164,0.98368454,-0.20859468,0.99999905,-0.104297355,0.99999905,-1.4901161e-08],"pill":[0.70710695,-0.7071067,0.8345046,-0.57970905,0.9193162,-0.40972537,0.9388399,-0.21985734,0.94170856,-0.19195819,0.9445772,-0.16405904,0.94744635,-0.13615984,0.9462347,0.08313513,0.85858226,0.2931037,0.70351505,0.4481709,0.61840034,0.5332856,0.53328586,0.61840034,0.4481709,0.70351505,0.29310346,0.8585825,0.08313513,0.94623446,-0.13616002,0.94744635,-0.16405928,0.9445772,-0.19195837,0.94170856,-0.21985757,0.9388399,-0.5995936,0.8997922,-0.89979225,0.59959364,-0.9388397,0.21985745,-0.9417085,0.19195819,-0.94457734,0.16405916,-0.94744617,0.1361599,-0.9462345,-0.08313525,-0.8585825,-0.29310346,-0.703515,-0.44817084,-0.6184002,-0.5332856,-0.5332854,-0.61840045,-0.44817066,-0.70351523,-0.29310334,-0.8585825,-0.08313477,-0.94623464,0.13616014,-0.9474461,0.1640594,-0.9445773,0.19195843,-0.94170845,0.21985745,-0.9388397,0.40972555,-0.91931593,0.5797093,-0.83450437,0.70710695,-0.7071067],"oval":[0.7071069,-0.7071068,0.7659764,-0.6482372,0.8069042,-0.5714259,0.8264643,-0.48009872,0.86558425,-0.29744458,0.81602836,-0.07168996,0.68869805,0.14750218,0.561368,0.36669397,0.36669397,0.561368,0.14750206,0.6886982,-0.071689844,0.81602824,-0.29744458,0.86558414,-0.48009872,0.8264642,-0.6627528,0.7873442,-0.78734434,0.66275275,-0.8264643,0.4800985,-0.86558425,0.29744446,-0.81602836,0.071689844,-0.68869823,-0.14750212,-0.56136817,-0.36669403,-0.36669397,-0.561368,-0.14750165,-0.6886983,0.07169032,-0.81602836,0.29744482,-0.86558425,0.48009896,-0.82646424,0.571426,-0.8069042,0.6482373,-0.7659764,0.7071069,-0.7071068],"diamond":[-6.7055225e-08,0.99999976,-0.054982588,0.99999976,-0.109965116,0.98501116,-0.15857214,0.9550339,-0.20547271,0.92610896,-0.258465,0.8574494,-0.36444956,0.7201302,-0.49971747,0.54487,-0.6349853,0.36960983,-0.7702532,0.19434977,-0.8586243,0.07985163,-0.85862434,-0.07985169,-0.77025324,-0.19434988,-0.6349853,-0.36961007,-0.4997174,-0.5448702,-0.36444956,-0.7201303,-0.258465,-0.85744935,-0.20547277,-0.92610884,-0.15857214,-0.9550339,-0.061358035,-1.0149888,0.061357975,-1.0149888,0.15857208,-0.9550339,0.20547271,-0.92610884,0.25846493,-0.8574493,0.36444938,-0.7201302,0.49971735,-0.5448701,0.6349853,-0.3696099,0.7702532,-0.1943497,0.8586242,-0.07985157,0.8586242,0.07985175,0.7702532,0.19434988,0.6349852,0.36960995,0.49971735,0.54487014,0.36444938,0.7201302,0.2584648,0.8574494,0.20547259,0.92610896,0.15857196,0.9550339,0.10996497,0.98501116,0.054982454,0.99999976,-6.7055225e-08,0.99999976],"cookie":[0.0,-1.0,0.07494998,-1.0,0.14989996,-0.973073,0.20925784,-0.91921884,0.26963854,-0.8644368,0.34909415,-0.8355174,0.43056166,-0.8386708,0.5907366,-0.844871,0.72945523,-0.72847223,0.75116336,-0.5696541,0.7622044,-0.48887664,0.80448174,-0.41565,0.86891663,-0.36569935,0.9956031,-0.26749063,1.0270481,-0.08915722,0.94159114,0.046458244,0.89812636,0.11543441,0.8834435,0.19870472,0.9006958,0.27838695,0.93461597,0.43505168,0.8440738,0.5918753,0.6914377,0.6408322,0.6138048,0.6657324,0.549032,0.72008324,0.51102924,0.79221284,0.43631136,0.9340285,0.26614773,0.99596286,0.11775315,0.9353535,0.042277336,0.9045267,-0.042277515,0.9045267,-0.117753625,0.9353535,-0.26614815,0.99596286,-0.43631172,0.9340284,-0.51102954,0.7922127,-0.5490322,0.720083,-0.6138051,0.665732,-0.6914381,0.64083195,-0.84407383,0.5918753,-0.93461597,0.43505168,-0.90069574,0.2783867,-0.8834434,0.19870436,-0.8981261,0.11543429,-0.94159126,0.04645765,-1.0270481,-0.08915788,-0.995603,-0.2674911,-0.86891645,-0.36569983,-0.8044816,-0.4156503,-0.7622042,-0.48887706,-0.7511631,-0.56965446,-0.72945505,-0.72847253,-0.59073645,-0.84487116,-0.43056142,-0.8386709,-0.3490939,-0.83551735,-0.2696383,-0.8644368,-0.20925772,-0.9192189,-0.14989996,-0.97307295,-0.07494998,-1.0,0.0,-1.0],"burst":[1.6734004e-05,-0.99999964,0.004110813,-1.0000052,0.008207619,-0.99796176,0.010504603,-0.99386716,0.06635976,-0.89429927,0.12221491,-0.7947314,0.17807019,-0.6951635,0.18137753,-0.68926764,0.18889809,-0.68726325,0.1947012,-0.6907309,0.29242253,-0.74912643,0.3901441,-0.80752194,0.48786557,-0.86591744,0.4959259,-0.870734,0.506147,-0.864851,0.5060308,-0.85546196,0.50461876,-0.741306,0.50320685,-0.62715006,0.50179493,-0.51299417,0.50171137,-0.5062345,0.5072222,-0.5007384,0.5139816,-0.50083995,0.62780845,-0.5025512,0.7416357,-0.50426245,0.8554627,-0.5059737,0.86485136,-0.50611484,0.87076163,-0.49590945,0.86596656,-0.48783636,0.8076656,-0.38968033,0.7493652,-0.2915244,0.69106436,-0.19336843,0.6876122,-0.18755627,0.6896366,-0.18004102,0.69554114,-0.17674929,0.79497373,-0.121317804,0.89440656,-0.0658862,0.9938394,-0.010454655,1.0020409,-0.0058825016,1.0020566,0.005910635,0.9938673,0.010504723,0.89429927,0.06635976,0.7947315,0.12221503,0.6951635,0.17807019,0.68926764,0.18137753,0.68726337,0.18889809,0.69073105,0.1947012,0.74912655,0.29242253,0.80752194,0.3901441,0.8659173,0.4878657,0.870734,0.49592614,0.8648509,0.50614715,0.85546184,0.5060309,0.74130595,0.5046189,0.62715006,0.50320697,0.51299405,0.50179493,0.5062344,0.50171137,0.50073826,0.5072222,0.50083995,0.5139816,0.5025511,0.62780845,0.50426257,0.7416357,0.5059737,0.85546255,0.50611496,0.86485136,0.49590945,0.87076163,0.48783636,0.86596644,0.3896804,0.8076656,0.2915243,0.749365,0.19336843,0.69106424,0.18755615,0.68761206,0.1800412,0.68963647,0.17674935,0.695541,0.121317744,0.7949736,0.06588626,0.8944063,0.0104545355,0.99383914,0.0058823824,1.0020406,-0.0059106946,1.0020564,-0.010504663,0.99386704,-0.06635988,0.89429915,-0.12221503,0.7947314,-0.17807025,0.6951635,-0.18137765,0.68926775,-0.1888982,0.68726337,-0.1947012,0.69073105,-0.2924227,0.74912655,-0.39014423,0.80752194,-0.4878657,0.8659173,-0.49592602,0.870734,-0.506147,0.8648509,-0.5060309,0.85546184,-0.504619,0.7413058,-0.5032071,0.6271498,-0.5017952,0.51299393,-0.50171155,0.5062343,-0.50722235,0.50073814,-0.5139817,0.5008398,-0.6278087,0.5025511,-0.7416357,0.50426245,-0.8554627,0.5059737,-0.8648514,0.50611484,-0.87076163,0.49590945,-0.8659665,0.48783636,-0.80766577,0.3896804,-0.7493651,0.2915243,-0.69106436,0.19336843,-0.68761206,0.18755615,-0.68963647,0.18004107,-0.69554114,0.17674935,-0.79497385,0.12131786,-0.89440656,0.06588638,-0.9938392,0.010454774,-1.0020407,0.00588274,-1.0020565,-0.005910456,-0.99386716,-0.010504484,-0.89429927,-0.06635976,-0.7947314,-0.12221497,-0.6951635,-0.17807013,-0.68926764,-0.18137753,-0.68726325,-0.18889815,-0.6907309,-0.19470114,-0.74912643,-0.2924226,-0.807522,-0.390144,-0.8659175,-0.4878654,-0.8707341,-0.49592572,-0.8648511,-0.5061468,-0.855462,-0.5060306,-0.74130607,-0.50461876,-0.6271502,-0.50320685,-0.51299417,-0.50179493,-0.5062345,-0.50171137,-0.5007384,-0.5072222,-0.50084007,-0.5139816,-0.5025512,-0.6278087,-0.5042624,-0.7416357,-0.5059736,-0.85546273,-0.5061147,-0.86485153,-0.4959094,-0.8707617,-0.48783624,-0.86596656,-0.38968027,-0.8076658,-0.2915244,-0.7493651,-0.19336843,-0.6910643,-0.1875562,-0.68761206,-0.18004096,-0.68963647,-0.17674929,-0.69554114,-0.12131786,-0.79497385,-0.06588626,-0.89440656,-0.010454774,-0.99383926,-0.008168697,-0.99794,-0.004077345,-0.9999943,1.6734004e-05,-0.99999964],"sunny":[1.0,7.450581e-09,1.0,0.03634134,0.9874656,0.07268268,0.96239686,0.10209942,0.9111545,0.16222918,0.8599124,0.22235894,0.80867016,0.28248882,0.7871852,0.30770028,0.7742008,0.33904707,0.7715658,0.3720665,0.76528144,0.4508183,0.75899696,0.52957034,0.7527125,0.60832214,0.74656355,0.6853763,0.6853763,0.74656343,0.60832214,0.7527125,0.52957034,0.75899696,0.4508183,0.76528144,0.3720665,0.7715659,0.33904696,0.7742009,0.30770028,0.7871852,0.28248882,0.80867016,0.22235894,0.8599124,0.16222906,0.9111545,0.1020993,0.96239686,0.04326582,1.0125344,-0.043266,1.0125344,-0.10209942,0.96239686,-0.16222918,0.9111545,-0.22235906,0.8599124,-0.28248882,0.80867016,-0.30770028,0.7871852,-0.33904707,0.7742008,-0.3720665,0.7715658,-0.45081842,0.76528144,-0.5295703,0.75899696,-0.6083222,0.7527125,-0.6853763,0.74656355,-0.7465635,0.6853764,-0.75271255,0.60832226,-0.75899696,0.52957034,-0.7652815,0.4508183,-0.77156603,0.37206626,-0.774201,0.33904684,-0.78718525,0.30770016,-0.8086703,0.28248858,-0.85991246,0.22235882,-0.9111547,0.16222906,-0.96239686,0.1020993,-1.0125344,0.04326582,-1.0125344,-0.043266058,-0.9623968,-0.10209948,-0.91115457,-0.16222918,-0.85991234,-0.22235894,-0.80867016,-0.28248876,-0.7871851,-0.30770028,-0.77420086,-0.33904696,-0.7715658,-0.37206638,-0.7652814,-0.45081842,-0.7589969,-0.5295704,-0.75271237,-0.6083224,-0.7465634,-0.6853764,-0.68537617,-0.7465636,-0.60832214,-0.7527126,-0.52957016,-0.7589971,-0.45081818,-0.76528156,-0.37206626,-0.771566,-0.33904672,-0.7742009,-0.30769998,-0.78718525,-0.28248847,-0.80867034,-0.22235876,-0.85991246,-0.16222906,-0.9111547,-0.10209936,-0.9623968,-0.04326594,-1.0125344,0.04326594,-1.0125344,0.10209942,-0.96239686,0.1622293,-0.91115457,0.22235906,-0.85991234,0.28248894,-0.8086701,0.3077004,-0.7871851,0.33904707,-0.77420074,0.3720665,-0.77156574,0.45081854,-0.76528126,0.5295706,-0.7589968,0.6083224,-0.75271237,0.6853765,-0.7465634,0.7465638,-0.6853761,0.7527127,-0.60832196,0.7589971,-0.5295701,0.76528156,-0.4508183,0.7715659,-0.3720665,0.7742009,-0.33904696,0.7871852,-0.30770028,0.8086703,-0.2824887,0.8599124,-0.22235894,0.9111546,-0.16222918,0.96239686,-0.10209936,0.9874656,-0.07268265,1.0,-0.036341324,1.0,7.450581e-09],"flower":[-0.2599851,-0.62596416,-0.24244297,-0.6785906,-0.22490078,-0.731217,-0.20735866,-0.78384346,-0.18168855,-0.86085397,-0.1337977,-0.9285427,-0.0697211,-0.97838,-0.051751375,-0.9923564,-0.029640913,-0.9999546,-0.0068757534,-0.99997634,-0.0029301047,-0.9999801,0.0010157824,-0.9999839,0.0049614906,-0.99998766,0.02772665,-1.0000094,0.049851537,-0.9924537,0.06784797,-0.9785117,0.13201964,-0.92879736,0.18004024,-0.86120003,0.20585752,-0.7842392,0.22350037,-0.7316464,0.24114335,-0.67905354,0.25878632,-0.62646073,0.30840302,-0.6512691,0.3580197,-0.6760774,0.4076364,-0.7008857,0.4802425,-0.7371888,0.56196976,-0.75118804,0.642519,-0.7411194,0.6651083,-0.7382957,0.6861154,-0.7280339,0.7022282,-0.7119519,0.7050209,-0.70916456,0.7078136,-0.7063772,0.71060634,-0.7035898,0.726719,-0.68750787,0.73702097,-0.66652036,0.73988795,-0.6439365,0.75011075,-0.56340694,0.7362679,-0.48165286,0.7001041,-0.4089775,0.6753907,-0.35931337,0.65067744,-0.30964923,0.62596416,-0.25998503,0.67859054,-0.2424429,0.73121715,-0.22490072,0.78384364,-0.20735854,0.8608538,-0.18168849,0.92854285,-0.1337974,0.97837996,-0.0697211,0.99235654,-0.051751316,0.9999547,-0.029640913,0.9999764,-0.006875634,0.99998,-0.002929926,0.9999838,0.0010159016,0.9999876,0.00496161,1.0000093,0.02772665,0.9924537,0.049851537,0.9785116,0.06784785,0.9287971,0.13201976,0.8612001,0.18004024,0.78423905,0.20585763,0.7316462,0.22350061,0.6790534,0.24114335,0.6264607,0.25878632,0.65126884,0.3084029,0.67607725,0.3580196,0.7008858,0.40763628,0.7371887,0.48024237,0.75118804,0.56196964,0.7411194,0.6425189,0.7382958,0.6651083,0.728034,0.6861155,0.71195185,0.7022283,0.7091644,0.705021,0.706377,0.70781374,0.70358956,0.71060646,0.6875076,0.72671914,0.66652024,0.7370211,0.6439364,0.7398881,0.5634068,0.75011086,0.48165286,0.73626816,0.4089775,0.70010424,0.35931325,0.67539084,0.3096491,0.6506777,0.25998497,0.6259643,0.24244285,0.67859066,0.22490072,0.73121727,0.20735836,0.78384364,0.18168831,0.8608539,0.13379753,0.92854273,0.0697211,0.97837996,0.051751256,0.99235654,0.029640794,0.9999547,0.006875634,0.9999764,0.002929926,0.99998,-0.001015842,0.9999838,-0.0049614906,0.9999876,-0.027726531,1.0000093,-0.049851358,0.9924537,-0.06784779,0.9785117,-0.1320197,0.9287971,-0.18004006,0.86120033,-0.20585763,0.7842392,-0.22350055,0.7316463,-0.24114347,0.67905354,-0.25878638,0.6264607,-0.30840302,0.65126884,-0.35801965,0.67607725,-0.40763634,0.70088565,-0.48024243,0.7371886,-0.56197,0.7511879,-0.6425192,0.74111915,-0.6651085,0.73829556,-0.6861155,0.7280338,-0.7022283,0.71195173,-0.705021,0.70916426,-0.70781386,0.7063769,-0.7106066,0.70358944,-0.7267193,0.6875075,-0.7370213,0.6665201,-0.7398882,0.6439363,-0.750111,0.5634066,-0.73626816,0.48165262,-0.7001041,0.40897727,-0.67539084,0.35931325,-0.65067744,0.3096491,-0.6259641,0.2599851,-0.67859054,0.24244297,-0.7312169,0.22490084,-0.7838433,0.20735872,-0.86085385,0.18168867,-0.92854273,0.13379765,-0.97838,0.06972098,-0.9923565,0.051751137,-0.9999546,0.029640794,-0.99997634,0.006875634,-0.9999801,0.002929926,-0.9999839,-0.001015842,-0.99998766,-0.0049615502,-1.0000094,-0.02772671,-0.9924537,-0.049851596,-0.9785117,-0.06784809,-0.9287971,-0.13201994,-0.8612002,-0.18004024,-0.78423905,-0.20585775,-0.7316463,-0.22350067,-0.6790535,-0.24114352,-0.6264607,-0.25878644,-0.65126896,-0.30840313,-0.6760773,-0.35801977,-0.70088553,-0.40763646,-0.7371886,-0.4802426,-0.7511878,-0.56197,-0.7411191,-0.64251924,-0.7382954,-0.6651086,-0.72803366,-0.6861156,-0.7119517,-0.7022285,-0.7091644,-0.7050211,-0.70637715,-0.70781374,-0.7035898,-0.71060634,-0.6875078,-0.72671914,-0.6665205,-0.7370211,-0.6439365,-0.739888,-0.5634069,-0.75011086,-0.48165286,-0.73626804,-0.4089775,-0.7001041,-0.35931343,-0.6753908,-0.3096493,-0.65067744,-0.2599851,-0.62596416],"soft-burst":[-0.6372275,-0.4627949,-0.62301916,-0.48243394,-0.61555684,-0.50695354,-0.61752415,-0.5326443,-0.62218547,-0.59351504,-0.6268467,-0.6543858,-0.631508,-0.7152566,-0.6374899,-0.79337335,-0.5592004,-0.850495,-0.48663598,-0.82095814,-0.42976862,-0.7978106,-0.37290126,-0.77466315,-0.31603396,-0.7515156,-0.26830465,-0.73208773,-0.21352524,-0.7500086,-0.18650717,-0.7938897,-0.15449929,-0.8458751,-0.1224913,-0.8978604,-0.09048343,-0.9498458,-0.049406946,-1.0165597,0.047505856,-1.0167546,0.08885026,-0.95020646,0.121251106,-0.898054,0.15365195,-0.84590155,0.1860528,-0.7937491,0.2132473,-0.749977,0.26809835,-0.7322767,0.31574917,-0.7518964,0.3722005,-0.7751397,0.42865157,-0.79838294,0.48510265,-0.8216262,0.5575478,-0.85145473,0.63606644,-0.7946485,0.63039875,-0.71650827,0.62595725,-0.6552713,0.6215155,-0.5940343,0.617074,-0.5327973,0.6133461,-0.48140043,0.64731765,-0.43483984,0.6974001,-0.42270416,0.756732,-0.40832722,0.8160641,-0.39395022,0.875396,-0.3795733,0.9515383,-0.36112309,0.98167133,-0.26901364,0.9311564,-0.2091282,0.89156866,-0.16219717,0.8519814,-0.115266085,0.81239367,-0.068335,0.7791674,-0.028945327,0.7792835,0.028690815,0.81266785,0.06794667,0.8522179,0.11445236,0.891768,0.16095805,0.93131804,0.20746374,0.9820733,0.2671454,0.95231104,0.35937524,0.8762438,0.37813163,0.8166313,0.3928306,0.75701904,0.4075296,0.69740653,0.4222288,0.64737344,0.43456602,0.6135895,0.48126268,0.61752415,0.53264403,0.62218523,0.5935149,0.62684655,0.6543858,0.6315079,0.7152567,0.6374898,0.79337335,0.5592003,0.8504951,0.48663592,0.82095814,0.42976856,0.79781055,0.3729012,0.7746632,0.31603384,0.7515156,0.2683046,0.7320876,0.21352506,0.7500086,0.18650699,0.79388976,0.15449905,0.845875,0.12249112,0.8978605,0.09048319,0.9498458,0.049406767,1.0165596,-0.047506034,1.0167546,-0.08885044,0.9502063,-0.121251225,0.8980539,-0.15365207,0.8459017,-0.18605286,0.7937491,-0.21324718,0.7499771,-0.26809835,0.7322767,-0.31574917,0.7518964,-0.37220037,0.7751396,-0.42865145,0.798383,-0.48510265,0.8216262,-0.55754757,0.85145473,-0.6360663,0.79464865,-0.63039875,0.7165084,-0.62595713,0.6552713,-0.6215156,0.5940342,-0.617074,0.5327971,-0.61334616,0.4814005,-0.64731765,0.43483996,-0.6974001,0.42270422,-0.75673217,0.4083271,-0.8160642,0.39395022,-0.87539625,0.37957335,-0.9515383,0.36112309,-0.9816714,0.26901364,-0.93115646,0.20912814,-0.89156884,0.16219711,-0.8519813,0.115265846,-0.81239367,0.06833482,-0.7791675,0.028945208,-0.7792834,-0.028691173,-0.8126678,-0.06794685,-0.8522178,-0.1144526,-0.8917678,-0.16095823,-0.9313178,-0.20746398,-0.9820732,-0.26714575,-0.9523108,-0.3593756,-0.8762436,-0.37813193,-0.8166313,-0.39283097,-0.75701904,-0.40752995,-0.69740677,-0.42222887,-0.6723901,-0.4283974,-0.6514358,-0.44315585,-0.6372275,-0.4627949]}});
/* END EARLY MATERIAL GEOMETRY */

/* Material loading indicator browser adaptation. Apache-2.0.
 * Copyright 2024 The Android Open Source Project; 2026 Klaude contributors.
 * Geometry: unmodified MaterialShapes + AndroidX Morph export.
 * Motion: LoadingIndicatorAnimatorDelegate / AndroidX SpringForce.
 * See vendor/material-loading-{LICENSE,NOTICE,manifest}.txt/json and
 * docs/webui/material-loading-indicator.md for pinned sources and differences.
 */
"use strict";

// This public asset also runs synchronously in <head>, before the stylesheet.
// Share preference validation with the app so its first paint uses the saved
// palette/motion settings without weakening the no-inline-script CSP.
window.KlaudeAppearance ??= (() => {
  const key = "klaude.webui.appearance.v1";
  const palettes = Object.freeze(["slate", "lavender", "sage", "peach", "ocean", "rose", "teal", "amber",
    "crimson", "coral", "violet", "indigo", "emerald", "lime", "sky", "cocoa"]);
  const defaults = Object.freeze({ version: 1, theme: "system", palette: "lavender", reduced: false, chatDensity: "compact",
    colorSource: "preset", accent: "#65558f", variant: "tonal-spot", transparency: 0, loadingStyle: "expressive" });
  function read(value) {
    try {
      const data = JSON.parse(value === undefined ? localStorage.getItem(key) : value);
      if (data?.version === 1 && ["system", "light", "dark"].includes(data.theme) &&
          palettes.includes(data.palette) && typeof data.reduced === "boolean") {
        return { version: 1, theme: data.theme, palette: data.palette, reduced: data.reduced,
          chatDensity: ["comfortable", "compact"].includes(data.chatDensity) ? data.chatDensity : defaults.chatDensity,
          colorSource: ["preset", "custom", "image"].includes(data.colorSource) ? data.colorSource : "preset",
          accent: /^#[a-f0-9]{6}$/i.test(data.accent) ? data.accent : defaults.accent,
          variant: ["tonal-spot", "expressive", "fidelity", "content", "monochrome", "neutral", "vibrant", "rainbow", "fruit-salad"].includes(data.variant) ? data.variant : defaults.variant,
          transparency: Number.isInteger(data.transparency) && data.transparency >= 0 && data.transparency <= 20 ? data.transparency : 0,
          loadingStyle: ["expressive", "classic"].includes(data.loadingStyle) ? data.loadingStyle : defaults.loadingStyle };
      }
    } catch { /* Browser storage is optional; corrupt preferences keep safe defaults. */ }
    return { ...defaults };
  }
  const saved = read(), root = document.documentElement;
  root.dataset.theme = saved.theme;
  root.dataset.palette = saved.palette;
  root.dataset.motion = saved.reduced ? "reduced" : "full";
  root.dataset.chatDensity = saved.chatDensity;
  root.dataset.loadingStyle = saved.loadingStyle;
  window.KlaudeColors?.apply(saved);
  return Object.freeze({ key, palettes, defaults, read });
})();

// Keep a failed/slow startup recoverable even if the deferred app cannot run.
window.MaterialProgress ??= (() => {
  const svgNS = "http://www.w3.org/2000/svg";
  const duration = 150;
  const stallDuration = 15000;
  function create() {
    const element = document.createElement("span");
    element.className = "md3-linear-progress";
    element.setAttribute("role", "progressbar");
    element.setAttribute("aria-label", "Loading Klaude");
    element.setAttribute("aria-valuemin", "0");
    element.setAttribute("aria-valuemax", "100");
    element.setAttribute("aria-valuenow", "0");
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", "0 0 360 16");
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("focusable", "false");
    const path = "M8 8 C17 1 26 1 35 8 S53 15 62 8 S80 1 89 8 S107 15 116 8 S134 1 143 8 S161 15 170 8 S188 1 197 8 S215 15 224 8 S242 1 251 8 S269 15 278 8 S296 1 305 8 S323 15 332 8 S341 1 352 8";
    const track = document.createElementNS(svgNS, "path");
    track.classList.add("md3-linear-progress-track");
    track.setAttribute("d", path);
    const indicator = document.createElementNS(svgNS, "path");
    indicator.classList.add("md3-linear-progress-indicator");
    indicator.setAttribute("d", path);
    indicator.setAttribute("pathLength", "360");
    svg.append(track, indicator);
    element.append(svg);
    const started = performance.now();
    const update = now => {
      if (!element.isConnected) return;
      const value = Math.min(100, ((now - started) / duration) * 100);
      element.setAttribute("aria-valuenow", String(Math.round(value)));
      indicator.style.strokeDashoffset = String(360 - value * 3.6);
      if (value < 100) requestAnimationFrame(update);
    };
    requestAnimationFrame(update);
    return { element, complete: () => {
      element.setAttribute("aria-valuenow", "100");
      indicator.style.strokeDashoffset = "0";
    }};
  }
  return Object.freeze({ create, duration });
})();

if (!window.KlaudeStartup) {
  let indicator = null;
  let completeProgress = null;
  const mount = () => {
    const target = document.querySelector(".startup-progress");
    if (indicator || !target || !window.MaterialProgress || document.documentElement.dataset.startup !== "loading") return;
    const progress = MaterialProgress.create();
    indicator = progress.element;
    completeProgress = progress.complete;
    target.replaceChildren(indicator);
    observer.disconnect();
  };
  // The synchronous head asset runs before the splash markup exists. Mount as
  // soon as parsing provides its slot, without waiting for deferred app scripts.
  const observer = new MutationObserver(mount);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  const stalled = () => {
    if (document.documentElement.dataset.startup !== "loading") return;
    const status = document.getElementById("startup-status");
    if (status) status.textContent = "Still connecting. You can wait or reload.";
    const retry = document.getElementById("startup-retry");
    if (retry) retry.hidden = false;
  };
  const timer = setTimeout(stalled, MaterialProgress.stallDuration);
  document.addEventListener("click", event => {
    if (event.target instanceof Element && event.target.closest("#startup-retry")) location.reload();
  });
  window.addEventListener("error", event => {
    if (event.target instanceof HTMLScriptElement && new URL(event.target.src).pathname === "/app.js") stalled();
  }, true);
  window.KlaudeStartup = Object.freeze({ mount, complete: async () => {
    clearTimeout(timer); observer.disconnect();
    completeProgress?.();
    await new Promise(resolve => setTimeout(resolve, 240));
    indicator?.remove();
  }});
}

window.MaterialLoading ??= (() => {
  const geometry = window.MaterialLoadingGeometry;
  if (!geometry?.morphs?.length) return null;
  const svgNS = "http://www.w3.org/2000/svg";
  const interval = 800;
  const systemReduced = matchMedia("(prefers-reduced-motion: reduce)");
  const states = new Map();
  let scheduled = null;

  // Solve x(t) for CSS/Qt cubic curves. Independent interpolation over the
  // existing Apache-licensed AndroidX matched cubics; no QML code is copied.
  function bezier(progress, x1, y1, x2, y2) {
    if (progress <= 0) return 0;
    if (progress >= 1) return 1;
    const axis = (t, a, b) => 3 * (1-t) ** 2 * t * a + 3 * (1-t) * t*t * b + t ** 3;
    let low = 0, high = 1;
    for (let i = 0; i < 14; i++) {
      const mid = (low + high) / 2;
      if (axis(mid, x1, x2) < progress) low = mid; else high = mid;
    }
    return axis((low + high) / 2, y1, y2);
  }
  function frameAt(milliseconds) {
    const elapsed = Math.max(0, milliseconds);
    const step = Math.floor(elapsed / interval), time = elapsed % interval;
    // The first shape holds for 800ms; each leap then morphs over 200ms.
    const fraction = step ? bezier(Math.min(1, time / 200), .34, .8, .34, 1) : 0;
    const rotationProgress = Math.min(1, time / 350);
    const quad = rotationProgress < .5 ? 2 * rotationProgress ** 2 : 1 - (-2 * rotationProgress + 2) ** 2 / 2;
    const zoomProgress = step ? bezier(Math.min(1, time / 750), .2, 0, 0, 1) : 0;
    return { index: step ? (step - 1) % geometry.morphs.length : 0, progress: fraction,
      zoom: 1 + .2 * (1 - Math.abs(zoomProgress * 2 - 1)),
      rotation: (elapsed / 12000 * 360 + (step ? (step - 1 + quad) * 90 : 0)) % 360 };
  }
  function pathAt(frame) {
    const { start, end } = geometry.morphs[frame.index];
    const values = start.map((value, index) => value + (end[index] - value) * frame.progress);
    let path = `M${values[0]},${values[1]}`;
    for (let i = 2; i < values.length; i += 6) path += `C${values.slice(i, i + 6).join(",")}`;
    return path + "Z";
  }
  function draw(state, frame) {
    // Most of each 800ms cycle is a held shape. Rotation/zoom can continue
    // without rebuilding a cubic path or notifying DOM consumers every frame.
    if (state.frameIndex !== frame.index || state.frameProgress !== frame.progress) {
      state.path.setAttribute("d", pathAt(frame));
      state.frameIndex = frame.index; state.frameProgress = frame.progress;
    }
    state.group.setAttribute("transform", `rotate(${frame.rotation}) scale(${frame.zoom})`);
  }
  function reduced() {
    return systemReduced.matches || document.documentElement.dataset.motion === "reduced";
  }
  function schedule() {
    if (scheduled === null && !document.hidden && !reduced() && document.documentElement.dataset.loadingStyle !== 'classic' &&
        [...states.values()].some(state => state.visible)) scheduled = requestAnimationFrame(tick);
  }
  function tick(now) {
    scheduled = null;
    for (const [element, state] of states) {
      if (!element.isConnected) { visibility.unobserve(element); states.delete(element); continue; }
      if (!state.visible || document.hidden || reduced()) continue;
      if (state.last !== null) state.elapsed += now - state.last;
      state.last = now;
      draw(state, frameAt(state.elapsed));
    }
    schedule();
  }
  const visibility = new IntersectionObserver(entries => {
    for (const entry of entries) {
      const state = states.get(entry.target);
      if (!state) continue;
      state.visible = entry.isIntersecting && entry.intersectionRatio > 0;
      state.last = null;
    }
    schedule();
  });
  function resetMotion() {
    if (scheduled !== null) cancelAnimationFrame(scheduled);
    scheduled = null;
    for (const state of states.values()) {
      state.last = null;
      if (reduced()) draw(state, frameAt(0));
    }
    schedule();
  }
  systemReduced.addEventListener("change", resetMotion);
  document.addEventListener("visibilitychange", resetMotion);
  new MutationObserver(resetMotion).observe(document.documentElement,
    { attributes: true, attributeFilter: ["data-motion", "data-loading-style"] });
  // Removed placeholders must release their paths even if no animation is running
  // (for example, a reduced-motion user navigating through hundreds of pages).
  new MutationObserver(() => {
    for (const [element] of states) if (!element.isConnected) {
      visibility.unobserve(element); states.delete(element);
    }
  }).observe(document.documentElement, { childList: true, subtree: true });

  function create({ size = "small", contained = false, label = "" } = {}) {
    const element = document.createElement("span");
    element.className = "material-loading";
    element.dataset.size = ["small", "medium", "large"].includes(size) ? size : "small";
    element.dataset.contained = String(contained);
    if (label) {
      element.setAttribute("role", "progressbar"); element.setAttribute("aria-label", label);
    } else element.setAttribute("aria-hidden", "true");
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", "-24 -24 48 48");
    svg.setAttribute("aria-hidden", "true"); svg.setAttribute("focusable", "false");
    const group = document.createElementNS(svgNS, "g");
    const path = document.createElementNS(svgNS, "path");
    path.setAttribute("transform", "scale(16.8)"); path.setAttribute("fill", "currentColor");
    group.append(path); svg.append(group); element.append(svg);
    const state = { path, group, elapsed: 0, last: null, visible: false };
    draw(state, frameAt(0)); states.set(element, state); visibility.observe(element);
    return element;
  }
  return Object.freeze({ create, frameAt, pathAt,
    names: geometry.names, activeCount: () => states.size });
})();
window.KlaudeStartup?.mount();
"use strict";

// Klaude Expressive. Independent web components; no end-4 QML implementation is
// included. Measured design behavior and deviations: docs/webui/klaude-expressive-reference.md.
window.KlaudeExpressive = (() => {
  const root = document.documentElement;
  const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches || root.dataset.motion === 'reduced';
  const svgNS = 'http://www.w3.org/2000/svg';
  const closest = (target, selector) => target instanceof Element ? target.closest(selector) : null;
  let imageGeneration = 0;
  function shape(name, size = 48) {
    const points = window.MaterialLoadingGeometry.shapes?.[name];
    if (!points) return document.createElement('span');
    const svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('viewBox', '-1 -1 2 2'); svg.setAttribute('width', size); svg.setAttribute('height', size);
    svg.setAttribute('aria-hidden', 'true'); svg.setAttribute('focusable', 'false');
    svg.classList.add('material-shape');
    const path = document.createElementNS(svgNS, 'path');
    let d = `M${points[0]},${points[1]}`;
    for (let i = 2; i < points.length; i += 6) d += `C${points.slice(i, i + 6).join(',')}`;
    path.setAttribute('d', d + 'Z'); path.setAttribute('fill', 'currentColor'); svg.append(path);
    return svg;
  }
  function themePreview(value, sync = false) {
    if (sync) {
      const source = document.querySelector(`input[name="color-source"][value="${value.colorSource || 'preset'}"]`);
      if (source) source.checked = true;
      for (const [id, next] of Object.entries({ 'theme-accent': value.accent || '#65558f',
        'theme-variant': value.variant || 'tonal-spot', 'theme-transparency': value.transparency || 0,
        'theme-loading-style': value.loadingStyle || 'expressive' })) {
        const input = document.getElementById(id); if (input) input.value = next;
      }
    }
    for (const input of document.querySelectorAll('input[name="theme-variant-choice"]'))
      input.checked = input.value === (value.variant || 'tonal-spot');
    const accent = document.getElementById('theme-accent-value');
    if (accent) accent.textContent = value.accent || '#65558f';
    const transparency = document.getElementById('theme-transparency-value');
    if (transparency) transparency.textContent = `${value.transparency || 0}%`;
    const range = document.getElementById('theme-transparency');
    if (range) range.style.setProperty('--range-progress', `${(value.transparency || 0) * 5}%`);
  }
  function setupSegments() {
    const selector = '.segmented, .section-chips, .cp-tabs, .connection-filters, .settings-tabs, .file-view-modes, .cp-view-modes, .suggestions';
    const groups = new Map(), pending = new Set();
    let frame = 0;
    function queue(group) {
      if (!groups.has(group)) return;
      pending.add(group);
      if (!frame) frame = requestAnimationFrame(layout);
    }
    const resize = new ResizeObserver(entries => {
      for (const { target } of entries) queue(groups.has(target) ? target : target.parentElement);
    });
    function register(group) {
      const previous = groups.get(group), items = [...group.children].filter(item => item.matches('button, label'));
      if (!previous) resize.observe(group);
      for (const item of previous || []) if (!items.includes(item)) resize.unobserve(item);
      for (const item of items) if (!previous?.includes(item)) resize.observe(item);
      groups.set(group, items); queue(group);
    }
    function discover(element) {
      if (element.matches(selector)) register(element);
      for (const group of element.querySelectorAll(selector)) register(group);
    }
    function layout() {
      frame = 0;
      const updates = [];
      // Read all layout before changing markers. offset coordinates exclude the
      // press scale, so pointer feedback cannot change row membership.
      for (const group of pending) {
        const items = groups.get(group);
        if (!items || !group.isConnected) continue;
        const visible = items.filter(item => item.getClientRects().length && item.offsetWidth && item.offsetHeight);
        if (!visible.length) continue;
        const rows = [], heights = new Map(), rtl = getComputedStyle(group).direction === 'rtl';
        for (const item of visible) {
          const face = item.matches('label') ? item.querySelector('input + span') : item;
          heights.set(item, (face || item).offsetHeight / 2);
          let row = rows.find(row => Math.abs(row.top - item.offsetTop) <= 1);
          if (!row) { row = { top: item.offsetTop, items: [] }; rows.push(row); }
          row.items.push(item);
        }
        const starts = new Set(), ends = new Set();
        for (const row of rows) {
          row.items.sort((a, b) => (a.offsetLeft - b.offsetLeft) * (rtl ? -1 : 1));
          starts.add(row.items[0]); ends.add(row.items.at(-1));
        }
        updates.push({ group, items, starts, ends, heights });
      }
      pending.clear();
      for (const { group, items, starts, ends, heights } of updates) {
        group.setAttribute('data-segment-layout', '');
        for (const item of items) {
          item.toggleAttribute('data-segment-start', starts.has(item));
          item.toggleAttribute('data-segment-end', ends.has(item));
          // Animate to the real half-height, like the reference. A 9999px pill
          // would stay visually clamped through almost the entire transition.
          if (heights.has(item)) {
            const radius = `${heights.get(item)}px`;
            if (item.style.getPropertyValue('--segment-pill-radius') !== radius)
              item.style.setProperty('--segment-pill-radius', radius);
          }
        }
      }
    }
    discover(document.body);
    new MutationObserver(records => {
      const changed = new Set();
      for (const record of records) {
        changed.add(record.target);
        if (record.type === 'childList') for (const node of record.addedNodes)
          if (node instanceof Element) discover(node);
        const group = closest(record.target, selector);
        if (group) register(group);
      }
      for (const [group, items] of groups) {
        if (!group.isConnected || !group.matches(selector)) {
          resize.unobserve(group); for (const item of items) resize.unobserve(item);
          groups.delete(group); pending.delete(group);
        } else if ([...changed].some(element => element.contains(group))) queue(group);
      }
    }).observe(document.body, { subtree: true, childList: true, attributes: true,
      attributeFilter: ['hidden', 'open', 'class', 'dir'] });
    const refresh = () => { for (const group of groups.keys()) queue(group); };
    window.addEventListener('resize', refresh);
    document.fonts.ready.then(refresh);
  }
  function setup() {
    for (const element of document.querySelectorAll('[data-material-shape]')) element.append(shape(element.dataset.materialShape));
    const emblem = document.querySelector('.welcome-emblem');
    if (emblem) { const backing = shape('cookie', 90); backing.classList.add('welcome-shape'); emblem.prepend(backing); }
    themePreview(appearance, true);
    // The source uses wrapping connected choices, rather than a dropdown, for
    // palette variants. The existing select remains the single form value.
    const variants = document.createElement('fieldset'), variantLegend = document.createElement('legend');
    variantLegend.textContent = 'Material palette variant'; variants.append(variantLegend);
    const variantChoices = document.createElement('div'); variantChoices.className = 'theme-variant-options segmented';
    for (const option of byId('theme-variant').options) {
      const label = document.createElement('label'), input = document.createElement('input'), caption = document.createElement('span');
      input.type = 'radio'; input.name = 'theme-variant-choice'; input.value = option.value;
      input.checked = option.value === byId('theme-variant').value; caption.textContent = option.text;
      input.onchange = () => { byId('theme-variant').value = input.value; byId('theme-variant').dispatchEvent(new Event('change')); };
      label.append(input, caption); variantChoices.append(label);
    }
    variants.append(variantChoices);
    const variantLabel = document.querySelector('.theme-variant-label');
    byId('theme-variant').hidden = true;
    variants.append(byId('theme-variant')); variantLabel.replaceWith(variants);
    setupSegments();
    const preview = () => { applyAppearance(appearanceDraft()); byId('theme-status').textContent = 'Preview · not saved'; };
    for (const id of ['theme-accent', 'theme-transparency']) byId(id).addEventListener('input', () => {
      if (id === 'theme-accent') document.querySelector('input[name="color-source"][value="custom"]').checked = true;
      preview();
    });
    byId('theme-image-choose').addEventListener('click', () => byId('theme-image').click());
    byId('theme-image').addEventListener('change', async event => {
      const generation = ++imageGeneration, file = event.target.files[0]; event.target.value = '';
      if (!file) return;
      const button = byId('theme-image-choose'), status = byId('theme-image-status');
      button.disabled = true; status.textContent = 'Finding colors on this device…';
      try {
        const accent = await window.KlaudeColors.fromImage(file);
        if (generation !== imageGeneration) return;
        byId('theme-accent').value = accent;
        document.querySelector('input[name="color-source"][value="image"]').checked = true;
        preview(); status.textContent = 'Palette ready. Apply changes to save the accent.';
      } catch (error) { if (generation === imageGeneration) status.textContent = error.message; }
      finally { if (generation === imageGeneration) button.disabled = false; }
    });
    function clearImage() {
      imageGeneration++; byId('theme-image-choose').disabled = false; byId('theme-image-status').textContent = '';
    }
    byId('theme-reset').addEventListener('click', clearImage);
    document.addEventListener('klaude-view', clearImage);
    document.addEventListener('klaude-auth-reset', clearImage);
    new MutationObserver(() => { if (byId('theme-settings').hidden) clearImage(); }).observe(
      byId('theme-settings'), { attributes: true, attributeFilter: ['hidden'] });

    // One bounded, interruptible ripple per pressed button. The state layer is a
    // pseudo element, leaving labels/DOM identity and all existing handlers alone.
    const ripples = new WeakMap();
    function press(button, x, y) {
      if (!button || button.disabled || reduced() || button.matches('.file-open, .cp-file-preview')) return;
      const box = button.getBoundingClientRect();
      button.style.setProperty('--ripple-x', `${x ?? box.width / 2}px`);
      button.style.setProperty('--ripple-y', `${y ?? box.height / 2}px`);
      ripples.get(button)?.cancel();
      const ripple = button.animate([{ opacity: .18, transform: 'scale(0)' },
        { opacity: .08, offset: .7, transform: 'scale(1)' }, { opacity: 0, transform: 'scale(1)' }],
        { duration: 1200, easing: 'cubic-bezier(0,0,0,1)', pseudoElement: '::after' });
      ripples.set(button, ripple);
    }
    document.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      const button = closest(event.target, 'button'); if (!button) return;
      const box = button.getBoundingClientRect(); press(button, event.clientX - box.left, event.clientY - box.top);
    });
    document.addEventListener('keydown', event => {
      if (!event.repeat && ['Enter', ' '].includes(event.key)) press(closest(event.target, 'button'));
    });
    // Native radios retain their arrow/Space behavior. Independent toolbar
    // buttons gain the same predictable Home/End and arrow-key navigation.
    document.addEventListener('keydown', event => {
      const group = closest(event.target, '.section-chips, .file-view-modes, .cp-view-modes, .connection-filters');
      if (event.defaultPrevented || !group || group.getAttribute('role') === 'tablist' ||
          !group.querySelector('[aria-pressed]') || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      const buttons = [...group.querySelectorAll('button')].filter(button => !button.disabled && !button.hidden);
      const index = buttons.indexOf(event.target); if (index < 0) return;
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 :
        (index + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
      event.preventDefault(); buttons[next].focus(); buttons[next].click();
    });
    // Spatial gallery navigation uses actual rendered cell positions, so columns
    // adapt to panel width without a second layout implementation.
    document.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key) || event.altKey || event.ctrlKey || event.metaKey) return;
      const button = closest(event.target, '.file-open'), grid = button?.closest('[data-view]');
      if (!grid) return;
      const buttons = [...grid.querySelectorAll('.file-open')], index = buttons.indexOf(button);
      const rect = button.getBoundingClientRect();
      let next;
      if (event.key === 'Home') next = buttons[0];
      else if (event.key === 'End') next = buttons.at(-1);
      else if (['ArrowLeft', 'ArrowRight'].includes(event.key)) next = buttons[index + (event.key === 'ArrowRight' ? 1 : -1)];
      else {
        const direction = event.key === 'ArrowDown' ? 1 : -1;
        next = buttons.filter(candidate => (candidate.getBoundingClientRect().top - rect.top) * direction > 4)
          .sort((a, b) => {
            const score = candidate => { const r = candidate.getBoundingClientRect();
              return Math.abs(r.top - rect.top) * 2 + Math.abs(r.left - rect.left); };
            return score(a) - score(b);
          })[0];
      }
      if (next) { event.preventDefault(); next.focus({ preventScroll: true }); next.scrollIntoView({ block: 'nearest' }); }
    });
    setupTooltips();
    setupCommands();
  }
  function setupTooltips() {
    const tooltip = document.createElement('div'); tooltip.id = 'expressive-tooltip';
    tooltip.className = 'expressive-tooltip'; tooltip.setAttribute('role', 'tooltip'); tooltip.setAttribute('popover', 'manual');
    document.body.append(tooltip); let target, nativeTitle = '';
    function hide() {
      if (target) {
        const descriptions = (target.getAttribute('aria-describedby') || '').split(/\s+/).filter(id => id && id !== tooltip.id);
        if (descriptions.length) target.setAttribute('aria-describedby', descriptions.join(' ')); else target.removeAttribute('aria-describedby');
        if (nativeTitle && !target.title) target.title = nativeTitle;
      }
      target = null; nativeTitle = ''; if (tooltip.matches(':popover-open')) tooltip.hidePopover();
    }
    function show(element) {
      if (!element || element === target) return;
      hide(); const label = element.title || element.getAttribute('aria-label');
      if (!label) return;
      target = element; nativeTitle = element.title; if (nativeTitle) element.title = '';
      tooltip.textContent = label;
      element.setAttribute('aria-describedby', [element.getAttribute('aria-describedby'), tooltip.id].filter(Boolean).join(' '));
      tooltip.showPopover();
      const rect = element.getBoundingClientRect(), box = tooltip.getBoundingClientRect();
      tooltip.style.left = `${Math.max(8, Math.min(innerWidth - box.width - 8, rect.left + (rect.width - box.width) / 2))}px`;
      tooltip.style.top = `${rect.bottom + box.height + 12 < innerHeight ? rect.bottom + 6 : Math.max(8, rect.top - box.height - 6)}px`;
    }
    const owner = event => closest(event.target, 'button[title], .icon-button[aria-label], [data-tooltip]');
    document.addEventListener('pointerover', event => { if (event.pointerType !== 'touch') show(owner(event)); });
    document.addEventListener('pointerout', event => { if (target && !target.contains(event.relatedTarget)) hide(); });
    document.addEventListener('focusin', event => { if (event.target instanceof Element && event.target.matches(':focus-visible')) show(owner(event)); });
    document.addEventListener('focusout', hide);
    document.addEventListener('pointerdown', hide);
    document.addEventListener('scroll', hide, true);
    document.addEventListener('keydown', event => { if (event.key === 'Escape') hide(); });
    document.addEventListener('klaude-auth-reset', hide);
  }
  function setupCommands() {
    const text = (tag, value, className = '') => { const element = document.createElement(tag);
      element.textContent = value; element.className = className; return element; };
    const mac = /Mac|iPhone|iPad/.test(navigator.platform), mod = mac ? '⌘' : 'Ctrl';
    const trigger = text('button', '', 'icon-button command-trigger'); trigger.id = 'command-open'; trigger.type = 'button';
    trigger.setAttribute('aria-label', 'Search commands'); trigger.title = `Search commands (${mod}+K)`;
    trigger.setAttribute('aria-haspopup', 'dialog'); trigger.setAttribute('aria-controls', 'command-palette');
    trigger.append(libraryIcon('search')); document.querySelector('.topbar-actions').prepend(trigger);
    const dialog = text('dialog', '', 'command-palette domain-dialog'); dialog.id = 'command-palette';
    dialog.setAttribute('aria-labelledby', 'command-title');
    const heading = text('div', '', 'dialog-heading'), title = text('h2', 'Find your next action'); title.id = 'command-title';
    const close = text('button', '', 'icon-button quiet'); close.type = 'button'; close.setAttribute('aria-label', 'Close commands');
    close.append(libraryIcon('close'));
    close.onclick = () => dialog.close(); heading.append(title, close);
    const search = text('input', ''); search.id = 'command-query'; search.type = 'search'; search.placeholder = 'Search commands, pages and conversations…';
    search.setAttribute('aria-label', 'Search commands'); search.setAttribute('role', 'combobox'); search.setAttribute('aria-autocomplete', 'list');
    search.setAttribute('aria-expanded', 'true'); search.setAttribute('aria-controls', 'command-results');
    const modes = text('div', '', 'section-chips command-modes'); modes.setAttribute('role', 'group'); modes.setAttribute('aria-label', 'Command search mode');
    const results = text('div', '', 'command-results'); results.id = 'command-results'; results.setAttribute('role', 'listbox'); results.setAttribute('aria-label', 'Commands');
    const status = text('p', '', 'muted command-count'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
    const footer = text('div', '↑ ↓ to explore · Enter to open · Esc to close', 'command-footer muted');
    let mode = 'commands', active = 0, actions = [], origin;
    for (const [value, label] of [['commands', 'Commands'], ['shortcuts', 'Shortcuts']]) {
      const button = text('button', label, 'quiet'); button.type = 'button'; button.dataset.mode = value;
      button.onclick = () => { mode = value; active = 0; render(); search.focus(); }; modes.append(button);
    }
    dialog.append(heading, search, modes, results, status, footer); document.body.append(dialog);
    const shortcuts = () => [
      ['Navigation', 'Search commands', `${mod}+K`], ['Navigation', 'Keyboard shortcuts', `${mod}+Shift+/`],
      ['Navigation', 'Open Settings', `${mod}+,`], ['Chat', 'Send message', enterSends() ? 'Enter' : 'Send button'],
      ['Chat', 'New line', enterSends() ? 'Shift+Enter' : 'Enter'],
      ['Dialogs', 'Dismiss dialog or menu', 'Esc'], ['Controls', 'Move between choices', '← → / ↑ ↓'],
      ['Library', 'Move between files', '← → ↑ ↓'], ['Library', 'First / last file', 'Home / End'],
      ['File preview', 'Previous / next image', '← / →'], ['File preview', 'Zoom', '+ / −'],
    ];
    function commands() {
      const pages = [['chat', 'Chat'], ['workspace', 'Workspaces'], ['library', 'Library'], ['models', 'Models'],
        ['integrations', 'Integrations'], ['activity', 'Activity'], ['settings', 'Settings']];
      const available = pages.map(([page, label]) => ({ group: 'Navigate', label: `Open ${label}`, run: () => showView(page) }));
      available.push({ group: 'Chat', label: 'Switch model', run: () => { showView('models'); byId('models-query').focus(); } },
        { group: 'Chat', label: 'Find a conversation', run: () => { toggleSessions(true); byId('session-search').focus(); } },
        { group: 'Chat', label: 'Toggle Context Panel', run: () => byId('inspector-toggle').click() },
        { group: 'Help', label: 'Show keyboard shortcuts', run: () => open('shortcuts') });
      if (!byId('new-session').disabled) available.push({ group: 'Chat', label: 'New conversation', run: () => byId('new-session').click() });
      if (!byId('cancel').disabled && !byId('cancel').hidden) available.push({ group: 'Chat', label: 'Cancel current turn', run: () => byId('cancel').click() });
      if (!latest?.active_turn_id && !latest?.queue?.length) for (const session of sessions.slice(0, 30)) {
        const id = session.id || session.session_id;
        if (id && id !== latest?.session_id && session.resumable) available.push({ group: 'Conversations', label: session.title || session.name || id, run: () => switchSession(id) });
      }
      return available;
    }
    function select(index) {
      active = Math.max(0, Math.min(actions.length - 1, index));
      for (const [i, option] of [...results.querySelectorAll('[role="option"]')].entries()) option.setAttribute('aria-selected', String(i === active));
      const selected = results.querySelector('[aria-selected="true"]');
      if (selected) { search.setAttribute('aria-activedescendant', selected.id); selected.scrollIntoView({ block: 'nearest' }); }
      else search.removeAttribute('aria-activedescendant');
    }
    function render() {
      for (const button of modes.children) button.setAttribute('aria-pressed', String(button.dataset.mode === mode));
      const query = search.value.trim().toLocaleLowerCase();
      const all = mode === 'shortcuts' ? shortcuts().map(([group, label, key]) => ({ group, label, key })) : commands();
      actions = all.filter(action => `${action.group} ${action.label} ${action.key || ''}`.toLocaleLowerCase().includes(query));
      results.replaceChildren(); let previous = '', group;
      for (const [index, action] of actions.entries()) {
        if (action.group !== previous) {
          group = text('div', ''); group.setAttribute('role', 'group'); group.setAttribute('aria-label', action.group);
          const label = text('h3', action.group); label.setAttribute('aria-hidden', 'true'); group.append(label);
          results.append(group); previous = action.group;
        }
        const option = text('div', '', 'command-option'); option.id = `command-option-${index}`; option.setAttribute('role', 'option');
        option.append(text('span', action.label)); if (action.key) option.append(text('kbd', action.key));
        option.onclick = () => execute(index); group.append(option);
      }
      status.textContent = actions.length ? `${actions.length} ${mode === 'shortcuts' ? 'shortcuts' : 'actions'}` : 'No matches. Try a page or conversation name.';
      footer.hidden = mode === 'shortcuts'; select(0);
    }
    function execute(index) {
      const action = actions[index]; if (!action?.run) return;
      const run = action.run; dialog.close(); run();
    }
    function open(next = 'commands') {
      if (!authenticated || document.querySelector('dialog[open]')) return;
      origin = document.activeElement; mode = next; search.value = ''; dialog.showModal(); render(); search.focus();
    }
    trigger.onclick = () => open(); search.addEventListener('input', render);
    search.addEventListener('keydown', event => {
      if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
        if (['Home', 'End'].includes(event.key) && search.value) return;
        event.preventDefault(); select(event.key === 'Home' ? 0 : event.key === 'End' ? actions.length - 1 : active + (event.key === 'ArrowDown' ? 1 : -1));
      } else if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); execute(active); }
    });
    dialog.addEventListener('close', () => { search.value = ''; results.replaceChildren();
      if (origin?.isConnected && !origin.closest('[hidden], [inert]')) origin.focus({ preventScroll: true }); });
    dialog.addEventListener('keydown', event => {
      if (event.key === 'Escape') { event.preventDefault(); dialog.close(); }
    });
    document.addEventListener('klaude-auth-reset', () => { if (dialog.open) dialog.close(); trigger.hidden = true; });
    document.addEventListener('klaude-snapshot', () => { trigger.hidden = !authenticated; });
    document.addEventListener('keydown', event => {
      if (!authenticated || event.repeat || event.isComposing || event.altKey || !(mac ? event.metaKey : event.ctrlKey)) return;
      if (event.key.toLowerCase() === 'k' && !event.shiftKey) { event.preventDefault(); if (dialog.open) dialog.close(); else open(); }
      else if ((event.key === '?' || event.code === 'Slash') && event.shiftKey) { event.preventDefault(); open('shortcuts'); }
      else if (event.key === ',' && !event.shiftKey && !document.querySelector('dialog[open]')) { event.preventDefault(); showView('settings'); }
    });
    trigger.hidden = !authenticated;
  }
  function workspace(result, source, operation, path) {
    const pre = result.querySelector('pre');
    if (operation === 'file') {
      const language = typeof sourceLanguage === 'function' ? sourceLanguage({ filename: path }) : 'text';
      const code = document.createElement('code');
      if (window.ChatMarkdown?.highlight) ChatMarkdown.highlight(code, source, language);
      else code.textContent = source;
      pre.replaceChildren(code); pre.tabIndex = 0; pre.setAttribute('aria-label', `File contents: ${path}`);
      const toolbar = document.createElement('div'); toolbar.className = 'workspace-preview-toolbar';
      const type = document.createElement('span'); type.textContent = language === 'text' ? 'Plain text' : language.toUpperCase();
      const status = document.createElement('span'); status.setAttribute('role', 'status'); status.className = 'muted';
      const copy = document.createElement('button'); copy.type = 'button'; copy.className = 'quiet'; copy.textContent = 'Copy preview';
      copy.onclick = async () => {
        copy.disabled = true;
        const copied = await window.ChatMarkdown?.copyText(source);
        if (status.isConnected) status.textContent = copied ? 'Preview copied.' : 'Select the preview text to copy it.';
        copy.disabled = false;
      };
      toolbar.append(type, status, copy); result.insertBefore(toolbar, pre);
      return;
    }
    if (operation === 'diff') {
      pre.classList.add('workspace-diff'); pre.replaceChildren();
      for (const line of source.split('\n')) {
        const row = document.createElement('span'); row.textContent = line || '\u00a0';
        row.className = line.startsWith('+++') || line.startsWith('---') || line.startsWith('@@') || line.startsWith('diff ') ?
          'diff-heading' : line.startsWith('+') ? 'diff-added' : line.startsWith('-') ? 'diff-removed' : '';
        pre.append(row);
      }
      return;
    }
    if (operation !== 'files') return;
    // Parse only the service's documented d/f rows. Ambiguous filenames retain
    // the original text response; every navigation still passes the server jail.
    const lines = source.split('\n');
    if (source !== '(empty)' && !lines.every(line => /^[df] [^\x00-\x1f]+$/.test(line))) return;
    const crumbs = document.createElement('nav'); crumbs.className = 'workspace-breadcrumbs'; crumbs.setAttribute('aria-label', 'Workspace path');
    const navigate = (next, kind = 'files') => { byId('workspace-path').value = next; workspaceRead(kind); };
    function crumb(label, next) { const button = document.createElement('button'); button.type = 'button'; button.className = 'quiet';
      button.textContent = label; button.onclick = () => navigate(next); crumbs.append(button); }
    crumb('Workspace', '.');
    const parts = path.replace(/^\.\//, '').split('/').filter(part => part && part !== '.');
    if (!path.startsWith('/') && !parts.includes('..')) parts.forEach((part, index) => crumb(part, parts.slice(0, index + 1).join('/')));
    result.insertBefore(crumbs, pre);
    if (source === '(empty)') { pre.textContent = 'This directory is empty.'; return; }
    const list = document.createElement('div'); list.className = 'workspace-files'; list.setAttribute('role', 'list');
    for (const line of lines) {
      const directory = line[0] === 'd', filePath = line.slice(2);
      const button = document.createElement('button'); button.type = 'button'; button.className = 'workspace-file-row';
      const icon = document.createElementNS(svgNS, 'svg'); icon.setAttribute('viewBox', '0 0 24 24'); icon.classList.add('icon'); icon.setAttribute('aria-hidden', 'true');
      const outline = document.createElementNS(svgNS, 'path'); outline.setAttribute('fill', 'none'); outline.setAttribute('stroke', 'currentColor'); outline.setAttribute('stroke-width', '1.7');
      outline.setAttribute('d', directory ? 'M3 6h7l2 2h9v12H3Z' : 'M5 3h9l5 5v13H5ZM14 3v6h5M8 13h8M8 17h5'); icon.append(outline);
      const name = document.createElement('span'); name.textContent = filePath.split('/').at(-1);
      const kind = document.createElement('small'); kind.textContent = directory ? 'Folder' :
        name.textContent.includes('.') ? name.textContent.split('.').at(-1).toUpperCase() : 'File';
      button.append(icon, name, kind); button.setAttribute('aria-label', `${directory ? 'Open folder' : 'Read file'} ${filePath}`);
      button.onclick = () => navigate(filePath, directory ? 'files' : 'file');
      const item = document.createElement('div'); item.setAttribute('role', 'listitem'); item.append(button); list.append(item);
    }
    pre.replaceWith(list);
  }
  document.addEventListener('DOMContentLoaded', setup, { once: true });
  return Object.freeze({ shape, themePreview, reduced, workspace });
})();
/* END BUNDLED MATERIAL LOADING */

const byId = (id) => document.getElementById(id);
const messages = byId("messages");
const chatResponseStatus = byId("chat-response-status");
const notice = byId("notice");
const prompt = byId("prompt");
const activity = byId("activity");
const approvals = byId("approvals");
const questions = byId("questions");
const queue = byId("queue");
let csrf = "";
let clientId = "";
let cursor = "";
let eventCursor = "";
let stream = null;
let pending = false;
let chatSubmission = null;
let latest = null;
let linkedMessage = null;
let messageHighlightTimer = null;
let pendingIntent = null;
let pendingSessionChoice = null;
let pendingRuntimeChoice = null;
let localModels = [];
let pollTimer = null;
let sessionsLoad = 0;
let sessionsLoaded = false;
let modelsLoad = 0;
let workspaceLoad = 0;
let workspaceOperation = "files";
let authenticated = false;
let authEpoch = 0;
let loginMethod = "password";
const viewNames = ["chat", "workspace", "library", "models", "integrations", "activity", "settings"];
let runtimeChoiceInFlight = false;
let currentView = "chat";
let sessions = [];
let approvalSignature = "";
let questionSignature = "";
const layout = document.querySelector(".layout");
layout.inert = true;
byId("logout").disabled = true;
const narrowScreen = matchMedia("(max-width: 850px)");
const compactInspector = matchMedia("(max-width: 1240px)");
const systemMotion = matchMedia("(prefers-reduced-motion: reduce)");
const { key: preferenceKey, palettes: paletteNames, defaults: defaultAppearance, read: readAppearance } = window.KlaudeAppearance;
let appearance = readAppearance();

// Delayed, owned placeholders: a stale request cannot clear a newer load.
const loadingStates = new WeakMap();
const activeLoading = new Set();
function loadingSkeleton(kind, count, label, artwork) {
  const root = document.createElement(["count", "text"].includes(kind) ? "span" : "div");
  root.className = `loading-skeleton skeleton-${kind}`;
  if (kind === "count") { root.setAttribute("aria-hidden", "true"); return root; }
  root.setAttribute("role", "status");
  const status = document.createElement("span");
  status.className = "visually-hidden";
  status.textContent = label;
  root.append(status);
  const feedback = document.createElement("span");
  feedback.className = "loading-feedback";
  feedback.setAttribute("aria-hidden", "true");
  const indicator = window.MaterialLoading?.create({ size: kind === "text" ? "small" : "large", contained: kind !== "text" });
  if (indicator) feedback.append(indicator);
  const description = document.createElement("span");
  description.textContent = label;
  feedback.append(description); root.append(feedback);
  for (let index = 0; index < count; index++) {
    const item = document.createElement(kind === "text" ? "span" : "div");
    item.className = `skeleton-item skeleton-${kind === "cards" ? "card" : "row"}`;
    item.setAttribute("aria-hidden", "true");
    if (kind === "detail" || kind === "cards" && artwork) {
      const image = document.createElement("span");
      image.className = "skeleton-image";
      item.append(image);
    }
    const lines = kind === "rows" || kind === "text" ? 1 : kind === "code" ? 8 : kind === "cards" ? 4 : 3;
    for (let line = 0; line < lines; line++) {
      const bar = document.createElement("span");
      bar.className = `skeleton-line skeleton-width-${(line + index) % 3}`;
      item.append(bar);
    }
    root.append(item);
  }
  return root;
}
function cancelLoading(target) {
  const state = loadingStates.get(target);
  if (!state) return;
  clearTimeout(state.timer);
  state.placeholder?.remove();
  target.classList.remove("is-loading");
  target.setAttribute("aria-busy", "false");
  loadingStates.delete(target);
  activeLoading.delete(state);
}
function beginLoading(target, { kind = "rows", count = 3, label = "Loading…", preserve = true, prepend = false, artwork = false } = {}) {
  if (!target) return () => false;
  cancelLoading(target);
  if (!preserve && !prepend) target.replaceChildren();
  const state = { target, placeholder: null, timer: null };
  loadingStates.set(target, state);
  activeLoading.add(state);
  target.setAttribute("aria-busy", "true");
  if (!preserve || !target.hasChildNodes()) {
    state.timer = setTimeout(() => {
      if (loadingStates.get(target) !== state || !target.isConnected) return;
      state.placeholder = loadingSkeleton(kind, count, label, artwork);
      if (target.closest('[role="status"]')) state.placeholder.removeAttribute("role");
      target.classList.add("is-loading");
      if (prepend) target.prepend(state.placeholder);
      else target.replaceChildren(state.placeholder);
    }, 120);
  }
  return () => {
    if (loadingStates.get(target) !== state) return false;
    cancelLoading(target);
    return true;
  };
}
function beginChatLoading() {
  const target = byId("chat-loading");
  if (!target) return () => {};
  if (!latest) byId("welcome").hidden = true;
  target.hidden = false;
  const finish = beginLoading(target, { kind: "conversation", count: 2, preserve: false, label: "Loading conversation…" });
  return () => { if (finish()) target.hidden = true; };
}
document.addEventListener("klaude-auth-reset", () => {
  for (const state of [...activeLoading]) cancelLoading(state.target);
  if (byId("chat-loading")) byId("chat-loading").hidden = true;
  sessionsLoad += 1;
  modelsLoad += 1;
  runtimeChoiceInFlight = false;
  workspaceLoad += 1;
  workspaceOperation = "files";
  sessionsLoaded = false;
  sessions = [];
  localModels = [];
  byId("session-list").replaceChildren();
  byId("model-status").textContent = "";
  byId("model-choice").replaceChildren();
  byId("model-connection-choice").replaceChildren();
  byId("effort-choice").replaceChildren();
  byId("workspace-result").textContent = "Browse a directory, read a file or inspect your changes.";
  delete byId("workspace-result").dataset.contentKey;
  interruptLatestScroll();
  byId("scroll-to-latest").hidden = true;
  renderChatScrollIndicator(false);
});

function nearLatestMessage() {
  return messages.scrollHeight - messages.scrollTop - messages.clientHeight < 100;
}

let chatScrollFrame = 0;
let latestScrollPending = false;
function interruptLatestScroll() {
  if (!latestScrollPending) return;
  latestScrollPending = false;
  messages.scrollTo({ top: messages.scrollTop, behavior: "instant" });
}
function renderChatScrollIndicator(working) {
  const button = byId("scroll-to-latest");
  const indicator = button.querySelector(".material-loading");
  const animated = working && Boolean(window.MaterialLoading);
  if (animated && !indicator) button.append(MaterialLoading.create({ size: "small" }));
  else if (!animated) indicator?.remove();
  button.dataset.working = String(animated);
  const label = working ? "Go to latest (Klaude is working)" : "Go to latest";
  button.setAttribute("aria-label", label);
  button.title = label;
}
function scheduleChatScrollControl() {
  if (chatScrollFrame) return;
  chatScrollFrame = requestAnimationFrame(() => {
    chatScrollFrame = 0;
    const button = byId("scroll-to-latest");
    const visible = authenticated && currentView === "chat" && messages.clientHeight > 0;
    const hidden = !visible || nearLatestMessage();
    if (hidden && visible && document.activeElement === button) messages.focus({ preventScroll: true });
    button.hidden = hidden;
    const activity = byId("agent-activity"), status = byId("chat-send-status");
    const working = !hidden && (status?.hidden === false ||
      activity?.hidden === false && activity.dataset.running === "true");
    renderChatScrollIndicator(working);
  });
}
messages.addEventListener("scroll", scheduleChatScrollControl, { passive: true });
for (const event of ["wheel", "touchstart", "pointerdown", "keydown"])
  messages.addEventListener(event, interruptLatestScroll, { passive: true });
messages.addEventListener("scrollend", () => {
  // Streaming may have extended the reply beyond the smooth scroll's target.
  if (latestScrollPending) {
    latestScrollPending = false;
    messages.scrollTo({ top: messages.scrollHeight, behavior: "instant" });
  }
  scheduleChatScrollControl();
});
const chatScrollResize = new ResizeObserver(scheduleChatScrollControl);
chatScrollResize.observe(messages);
// Markdown, attachments and activity details can change the remaining distance
// without scrolling or resizing the conversation viewport.
const chatScrollContent = new MutationObserver((changes) => {
  for (const change of changes) {
    if (change.target !== messages) continue;
    for (const node of change.removedNodes) if (node.nodeType === Node.ELEMENT_NODE) chatScrollResize.unobserve(node);
    for (const node of change.addedNodes) if (node.nodeType === Node.ELEMENT_NODE) chatScrollResize.observe(node);
  }
  scheduleChatScrollControl();
});
chatScrollContent.observe(messages, { childList: true, subtree: true, characterData: true,
  attributes: true, attributeFilter: ["hidden"] });
document.addEventListener("klaude-view", () => { interruptLatestScroll(); scheduleChatScrollControl(); });
document.addEventListener("klaude-chat-session-changed", interruptLatestScroll);
byId("scroll-to-latest").addEventListener("click", () => {
  const reduced = systemMotion.matches || document.documentElement.dataset.motion === "reduced";
  const smooth = !reduced && "onscrollend" in messages;
  latestScrollPending = smooth;
  messages.scrollTo({ top: messages.scrollHeight, behavior: smooth ? "smooth" : "instant" });
  messages.focus({ preventScroll: true });
});

// Shared file-only drag handling stays in an existing asset for running hosts.
window.FileDropUI = (() => {
  const destinations = [];
  const host = byId("main-content");
  let overlay, title, detail, note, expiry, depth = 0;
  function reset() { clearTimeout(expiry); depth = 0; if (overlay) overlay.hidden = true; }
  function keepAlive() {
    // External drags can disappear without dragend/dragleave (OS/browser cancellation).
    clearTimeout(expiry); expiry = setTimeout(reset, 1600);
  }
  function hasFiles(event) {
    return [...(event.dataTransfer?.types || [])].some(type =>
      type === "Files" || type === "application/x-klaude-library-artifact") ||
      [...(event.dataTransfer?.items || [])].some(item => item.kind === "file");
  }
  function destination(event) {
    if (!authenticated || document.querySelector("dialog[open]") ||
        !(event.target instanceof Node) || !host.contains(event.target)) return null;
    const library = [...(event.dataTransfer?.types || [])].includes("application/x-klaude-library-artifact");
    return destinations.find(item => item.active() && (!library || item.receiveLibrary));
  }
  function show(target) {
    if (!target) { if (overlay) overlay.hidden = true; return; }
    const state = target.state();
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "file-drop-overlay";
      overlay.setAttribute("role", "status");
      overlay.setAttribute("aria-live", "polite");
      overlay.setAttribute("aria-atomic", "true");
      const card = document.createElement("div");
      card.className = "file-drop-card";
      const artwork = document.createElement("div");
      artwork.className = "file-drop-artwork";
      artwork.setAttribute("aria-hidden", "true");
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 144 120");
      svg.setAttribute("fill", "none");
      svg.setAttribute("focusable", "false");
      svg.setAttribute("stroke-width", "2");
      svg.setAttribute("stroke-linecap", "round");
      svg.setAttribute("stroke-linejoin", "round");
      const shape = (tag, attributes, parent = svg) => {
        const node = document.createElementNS(svg.namespaceURI, tag);
        for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
        parent.append(node);
        return node;
      };
      const photo = shape("g", { transform: "rotate(-10 44 62)" });
      shape("rect", { x: 10, y: 28, width: 66, height: 68, rx: 14, class: "file-drop-photo" }, photo);
      shape("circle", { cx: 29, cy: 48, r: 5, class: "file-drop-photo-detail" }, photo);
      shape("path", { d: "m20 81 14-19 12 14 9-11 12 16", class: "file-drop-photo-detail" }, photo);
      shape("path", { d: "M62 12h28a6 6 0 0 1 4.2 1.8l16 16A6 6 0 0 1 112 34v62a10 10 0 0 1-10 10H62a10 10 0 0 1-10-10V22a10 10 0 0 1 10-10Z", class: "file-drop-document" });
      shape("path", { d: "M90 13v13a8 8 0 0 0 8 8h13", class: "file-drop-document-detail" });
      shape("path", { d: "M66 52h31M66 64h26M66 76h17", class: "file-drop-document-detail" });
      shape("circle", { cx: 112, cy: 96, r: 19, class: "file-drop-add" });
      shape("path", { d: "M112 88v16m-8-8h16", class: "file-drop-add-detail" });
      artwork.append(svg);
      title = document.createElement("strong");
      title.className = "file-drop-title";
      detail = document.createElement("p");
      note = document.createElement("span");
      note.className = "file-drop-note";
      card.append(artwork, title, detail, note);
      overlay.append(card); host.append(overlay);
    }
    overlay.dataset.allowed = String(state.allowed);
    for (const [element, value] of [[title, state.title], [detail, state.detail], [note, state.note]])
      if (element.textContent !== value) element.textContent = value;
    overlay.hidden = false;
    return state;
  }
  document.addEventListener("dragenter", event => {
    if (!hasFiles(event)) return;
    event.preventDefault(); keepAlive(); depth++; show(destination(event));
  });
  document.addEventListener("dragover", event => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    keepAlive();
    const state = show(destination(event));
    event.dataTransfer.dropEffect = state?.allowed ? "copy" : "none";
  });
  document.addEventListener("dragleave", event => {
    if (!hasFiles(event) && !depth) return;
    depth = Math.max(0, depth - 1);
    if (!depth || !event.relatedTarget && (event.clientX <= 0 || event.clientY <= 0 ||
        event.clientX >= innerWidth || event.clientY >= innerHeight)) reset();
  });
  document.addEventListener("drop", event => {
    if (!hasFiles(event)) return;
    // Prevent navigation even over a sidebar, another page, or an open dialog.
    event.preventDefault();
    const target = destination(event);
    reset();
    if (!target) return;
    const state = target.state();
    if (!state.allowed) { target.reject(state.detail); return; }
    const library = event.dataTransfer.getData("application/x-klaude-library-artifact");
    if (library) {
      try {
        if (library.length > 512) throw new Error("Invalid Library selection.");
        const item = JSON.parse(library);
        if (item.session !== latest?.session_id || !/^(document|media|research):[a-f0-9]{32}$/.test(item.id) ||
            !Number.isSafeInteger(item.revision) || item.revision < 1)
          throw new Error("Choose this Library file again for the current conversation.");
        Promise.resolve(target.receiveLibrary(item)).catch(error => target.reject(error.message));
      } catch (error) { target.reject(error.message); }
      return;
    }
    const items = [...(event.dataTransfer.items || [])];
    if (items.some(item => item.kind === "file" && item.webkitGetAsEntry?.()?.isDirectory)) {
      target.reject("Choose files instead of folders."); return;
    }
    const files = [...event.dataTransfer.files];
    if (!files.length) { target.reject("No readable files were dropped. Choose files from your device."); return; }
    const epoch = authEpoch;
    Promise.resolve().then(() => {
      if (authenticated && epoch === authEpoch && target.active()) return target.receive(files);
    }).catch(error => {
      if (authenticated && epoch === authEpoch && target.active()) target.reject(error.message);
    });
  });
  document.addEventListener("dragend", reset);
  document.addEventListener("keydown", event => { if (event.key === "Escape") reset(); });
  document.addEventListener("visibilitychange", () => { if (document.hidden) reset(); });
  window.addEventListener("blur", reset);
  for (const name of ["klaude-view", "klaude-chat-session-changed", "klaude-auth-reset"])
    document.addEventListener(name, reset);
  return Object.freeze({ register: target => destinations.push(target), reset });
})();

function resizePrompt() {
  prompt.style.height = "auto";
  prompt.style.height = `${prompt.scrollHeight}px`;
}
prompt.addEventListener("input", resizePrompt);
const desktopComposer = matchMedia("(any-hover: hover) and (any-pointer: fine)");
const enterSends = () => desktopComposer.matches || navigator.maxTouchPoints === 0;
function updateComposerHint() {
  byId("composer-keyboard-hint").textContent = enterSends() ?
    "Enter to send. Shift+Enter for a new line." : "Use Send to send your message.";
  prompt.setAttribute("aria-describedby", "composer-keyboard-hint");
}
updateComposerHint();
desktopComposer.addEventListener("change", updateComposerHint);
prompt.addEventListener("keydown", event => {
  if (!enterSends() || event.key !== "Enter" || event.shiftKey ||
      event.ctrlKey || event.metaKey || event.altKey || event.isComposing || event.keyCode === 229) return;
  event.preventDefault();
  if (!event.repeat && !pending && !byId("send").disabled) byId("composer").requestSubmit(byId("send"));
});

function applyAppearance(value, syncControls = false) {
  document.documentElement.dataset.theme = value.theme;
  document.documentElement.dataset.palette = value.palette;
  document.documentElement.dataset.motion = value.reduced ? "reduced" : "full";
  document.documentElement.dataset.chatDensity = value.chatDensity || defaultAppearance.chatDensity;
  document.documentElement.dataset.loadingStyle = value.loadingStyle || "expressive";
  window.KlaudeColors?.apply(value);
  window.KlaudeExpressive?.themePreview(value, syncControls);
  if (value.reduced || systemMotion.matches) {
    document.getAnimations().forEach((animation) => animation.cancel());
  }
  if (syncControls) {
    document.querySelector(`input[name="appearance"][value="${value.theme}"]`).checked = true;
    document.querySelector(`input[name="palette"][value="${value.palette}"]`).checked = true;
    byId("reduced-motion").checked = value.reduced;
    const density = document.querySelector(`input[name="chat-density"][value="${value.chatDensity || defaultAppearance.chatDensity}"]`);
    if (density) density.checked = true;
  }
  updateThemeActions();
}

function updateThemeActions() {
  const dirty = Object.entries(appearanceDraft()).some(([key, value]) => value !== appearance[key]);
  byId("theme-save-bar").hidden = !dirty;
  window.SettingsActions?.refresh();
}

function appearanceDraft() {
  return { version: 1,
    theme: document.querySelector('input[name="appearance"]:checked').value,
    palette: document.querySelector('input[name="palette"]:checked').value,
    reduced: byId("reduced-motion").checked,
    chatDensity: document.querySelector('input[name="chat-density"]:checked')?.value || defaultAppearance.chatDensity,
    colorSource: document.querySelector('input[name="color-source"]:checked')?.value || "preset",
    accent: byId("theme-accent")?.value || appearance.accent,
    variant: byId("theme-variant")?.value || "tonal-spot",
    transparency: Number(byId("theme-transparency")?.value || 0),
    loadingStyle: byId("theme-loading-style")?.value || "expressive" };
}

applyAppearance(appearance, true);
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => applyAppearance(appearanceDraft()));
systemMotion.addEventListener("change", () => {
  if (systemMotion.matches) document.getAnimations().forEach((animation) => animation.cancel());
});
for (const input of document.querySelectorAll('input[name="appearance"], input[name="palette"], input[name="chat-density"], #reduced-motion, input[name="color-source"], #theme-accent, #theme-variant, #theme-transparency, #theme-loading-style')) {
  input.addEventListener("change", () => {
    if (input.name === "palette") document.querySelector('input[name="color-source"][value="preset"]').checked = true;
    if (input.id === "theme-accent") document.querySelector('input[name="color-source"][value="custom"]').checked = true;
    applyAppearance(appearanceDraft());
    byId("theme-status").textContent = "Preview · not saved";
  });
}
byId("theme-apply").addEventListener("click", () => {
  const draft = appearanceDraft();
  try {
    localStorage.setItem(preferenceKey, JSON.stringify(draft));
    appearance = draft;
    byId("theme-status").textContent = "Saved on this device";
  } catch { byId("theme-status").textContent = "Could not save. Preview is temporary."; }
  updateThemeActions();
});
byId("theme-reset").addEventListener("click", () => {
  applyAppearance(appearance, true);
  byId("theme-status").textContent = "Preview discarded";
});
window.addEventListener("storage", (event) => {
  if (event.key !== preferenceKey && event.key !== null) return;
  appearance = readAppearance(event.key === null ? null : event.newValue);
  applyAppearance(appearance, true);
  byId("theme-status").textContent = "Updated from another tab";
});

function setConnection(connected, label) {
  byId("connection-state").textContent = label;
  document.querySelector(".topbar-context").dataset.connected = String(connected);
}

function toggleSessions(open) {
  const restoreFocus = !open && (byId("session-sidebar").contains(document.activeElement) ||
    document.activeElement === byId("drawer-scrim"));
  layout.classList.toggle("sessions-open", narrowScreen.matches && open);
  if (!narrowScreen.matches) layout.classList.toggle("sessions-collapsed", !open);
  byId("session-sidebar").inert = !open;
  byId("sessions-toggle").setAttribute("aria-expanded", String(open));
  byId("drawer-scrim").hidden = !narrowScreen.matches || !open;
  if (open && narrowScreen.matches) byId("new-session").focus();
  else if (restoreFocus) byId("sessions-toggle").focus();
}
byId("sessions-toggle").addEventListener("click", () => toggleSessions(narrowScreen.matches ?
  !layout.classList.contains("sessions-open") : layout.classList.contains("sessions-collapsed")));
byId("drawer-scrim").addEventListener("click", () => toggleSessions(false));
let contextPanelOpen;
try { contextPanelOpen = JSON.parse(sessionStorage.getItem("klaude.context-panel.open")); } catch { /* Use viewport default. */ }
if (typeof contextPanelOpen !== "boolean") contextPanelOpen = false;
function setContextPanel(open, focus = false) {
  contextPanelOpen = open;
  layout.classList.toggle("inspector-open", open);
  layout.classList.toggle("inspector-closed", !open);
  byId("inspector").inert = !open;
  byId("inspector-toggle").setAttribute("aria-expanded", String(open));
  try { sessionStorage.setItem("klaude.context-panel.open", JSON.stringify(open)); } catch { /* Optional persistence. */ }
  if (focus) (open ? byId("cp-tab-agent") : byId("inspector-toggle")).focus();
  document.dispatchEvent(new Event("klaude-context-panel"));
}
byId("inspector-toggle").setAttribute("aria-label", "Toggle context panel");
byId("inspector-toggle").addEventListener("click", () => setContextPanel(!contextPanelOpen, true));
function updatePanelLayout() {
  toggleSessions(!narrowScreen.matches && !layout.classList.contains("sessions-collapsed"));
  setContextPanel(contextPanelOpen);
}
compactInspector.addEventListener("change", updatePanelLayout);
narrowScreen.addEventListener("change", () => toggleSessions(!narrowScreen.matches && !layout.classList.contains("sessions-collapsed")));
updatePanelLayout();

// Resize the central surface from its own edges; side panels have no split lines.
window.ChatLayoutUI = (() => {
  const key = "klaude.webui.chat-width.v1";
  const main = byId("main-content");
  const handles = { left: byId("chat-resize-left"), right: byId("chat-resize-right") };
  const limits = { left: [216, 420], right: [280, 560] };
  const css = { left: "--session-width", right: "--context-width" };
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  let frame, drag, geometry;
  function read(value) {
    try {
      const parsed = JSON.parse(value === undefined ? localStorage.getItem(key) : value);
      if (parsed?.version === 1 && ["left", "right"].every(side => parsed[side] === null ||
          Number.isFinite(parsed[side]) && parsed[side] >= limits[side][0] && parsed[side] <= limits[side][1]))
        return { left: parsed.left, right: parsed.right };
    } catch { /* Browser storage is optional. */ }
    return { left: null, right: null };
  }
  let preference = read();
  function save() {
    try { localStorage.setItem(key, JSON.stringify({ version: 1, ...preference })); }
    catch { /* Keep the chosen layout for this page when storage is unavailable. */ }
  }
  function paint() {
    frame = null;
    if (layout.hidden || !layout.clientWidth) return;
    const style = getComputedStyle(layout);
    const available = layout.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight) -
      parseFloat(style.getPropertyValue("--rail-width"));
    const visible = { left: !narrowScreen.matches && !layout.classList.contains("sessions-collapsed"),
      right: !compactInspector.matches && contextPanelOpen };
    if (drag && !visible[drag.side]) finish(false);
    const sizes = {
      left: clamp(preference.left ?? parseFloat(style.getPropertyValue("--session-default-width")), ...limits.left),
      right: clamp(preference.right ?? parseFloat(style.getPropertyValue("--context-default-width")), ...limits.right),
    };
    // Preserve at least 400px for chat. A smaller viewport temporarily reduces
    // effective panel widths without overwriting the user's saved preferences.
    const used = Object.keys(handles).reduce((sum, side) => sum + (visible[side] ? sizes[side] : 0), 0);
    const excess = Math.max(0, used - (available - 400));
    if (excess) {
      const room = Object.keys(handles).reduce((sum, side) =>
        sum + (visible[side] ? sizes[side] - limits[side][0] : 0), 0);
      for (const side of Object.keys(handles)) if (visible[side] && room)
        sizes[side] -= Math.min(1, excess / room) * (sizes[side] - limits[side][0]);
    }
    for (const side of Object.keys(handles)) {
      const value = `${sizes[side]}px`;
      if (layout.style.getPropertyValue(css[side]) !== value) layout.style.setProperty(css[side], value);
    }
    const chatWidth = Math.round(main.getBoundingClientRect().width);
    geometry = { visible, sizes, available, bounds: {} };
    for (const side of Object.keys(handles)) {
      const other = side === "left" ? "right" : "left";
      const remaining = available - (visible[other] ? sizes[other] : 0);
      const max = Math.max(limits[side][0], Math.min(limits[side][1], remaining - 400));
      geometry.bounds[side] = [limits[side][0], max];
      const handle = handles[side], focused = document.activeElement === handle;
      handle.hidden = !visible[side];
      if (!visible[side] && focused) main.focus({ preventScroll: true });
      handle.setAttribute("aria-valuemin", String(Math.round(remaining - max)));
      handle.setAttribute("aria-valuemax", String(Math.round(remaining - limits[side][0])));
      handle.setAttribute("aria-valuenow", String(chatWidth));
      handle.setAttribute("aria-valuetext", `Chat ${chatWidth} pixels; ${side === "left" ? "conversations" : "context"} ${Math.round(sizes[side])} pixels`);
    }
  }
  function refresh() { if (!frame) frame = requestAnimationFrame(paint); }
  function change(side, value) {
    if (!geometry?.visible[side]) return;
    // Hold the opposite edge still when deliberately adjusting one edge.
    for (const other of Object.keys(handles)) if (geometry.visible[other]) preference[other] = geometry.sizes[other];
    preference[side] = Math.round(clamp(value, ...geometry.bounds[side]));
    paint();
  }
  function finish(commit) {
    if (!drag) return;
    const previous = drag; drag = null;
    if (!commit) preference = previous.preference;
    else if (previous.moved) save();
    handles[previous.side].removeAttribute("data-dragging");
    document.documentElement.classList.remove("resizing-chat");
    if (handles[previous.side].hasPointerCapture(previous.pointer))
      handles[previous.side].releasePointerCapture(previous.pointer);
    refresh();
  }
  for (const [side, handle] of Object.entries(handles)) {
    handle.addEventListener("pointerdown", event => {
      if (!event.isPrimary || event.button !== 0 || !geometry?.visible[side]) return;
      event.preventDefault(); finish(false); paint();
      drag = { side, pointer: event.pointerId, x: event.clientX, size: geometry.sizes[side],
        preference: { ...preference }, moved: false };
      handle.focus({ preventScroll: true }); handle.setPointerCapture(event.pointerId);
      handle.dataset.dragging = "true"; document.documentElement.classList.add("resizing-chat");
    });
    handle.addEventListener("pointermove", event => {
      if (!drag || drag.side !== side || drag.pointer !== event.pointerId) return;
      const delta = (event.clientX - drag.x) * (side === "left" ? 1 : -1);
      if (Math.abs(delta) < 2 && !drag.moved) return;
      drag.moved = true; change(side, drag.size + delta);
    });
    handle.addEventListener("pointerup", event => {
      if (drag?.pointer === event.pointerId) finish(true);
    });
    for (const event of ["pointercancel", "lostpointercapture"]) handle.addEventListener(event, () => finish(false));
    const reset = () => { finish(false); preference[side] = null; paint(); save(); };
    handle.addEventListener("dblclick", reset);
    handle.addEventListener("keydown", event => {
      if (!geometry?.visible[side]) return;
      const step = event.altKey ? 1 : event.shiftKey ? 40 : 10;
      if (event.key === "Enter") { event.preventDefault(); reset(); return; }
      let value;
      if (["ArrowLeft", "ArrowRight"].includes(event.key))
        value = geometry.sizes[side] + (event.key === "ArrowRight" ? step : -step) * (side === "left" ? 1 : -1);
      else if (event.key === "Home") value = geometry.bounds[side][1];
      else if (event.key === "End") value = geometry.bounds[side][0];
      else return;
      event.preventDefault(); change(side, value); save();
    });
  }
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && drag) { event.preventDefault(); event.stopPropagation(); finish(false); }
  }, true);
  window.addEventListener("blur", () => finish(false));
  document.addEventListener("klaude-auth-reset", () => finish(false));
  window.addEventListener("storage", event => {
    if (event.key !== key && event.key !== null) return;
    finish(false); preference = read(event.key === null ? null : event.newValue); refresh();
  });
  new ResizeObserver(refresh).observe(layout);
  new MutationObserver(refresh).observe(layout, { attributes: true, attributeFilter: ["class", "hidden"] });
  for (const media of [narrowScreen, compactInspector]) media.addEventListener("change", refresh);
  refresh();
  return Object.freeze({ refresh });
})();
// Native dialog backdrops target the dialog itself. Require a complete tap on
// that backdrop so form interactions and drags out of a dialog cannot dismiss it.
(() => {
  let press = null;
  function outside(dialog, event) {
    if (!dialog?.open || event.target !== dialog) return false;
    const bounds = dialog.getBoundingClientRect();
    return event.clientX < bounds.left || event.clientX > bounds.right ||
      event.clientY < bounds.top || event.clientY > bounds.bottom;
  }
  document.addEventListener("pointerdown", event => {
    const dialog = event.target instanceof HTMLDialogElement ? event.target : null;
    press = event.isPrimary && event.button === 0 && outside(dialog, event) ?
      { dialog, pointerId: event.pointerId, x: event.clientX, y: event.clientY } : null;
  }, true);
  document.addEventListener("pointermove", event => {
    if (press?.pointerId === event.pointerId &&
        Math.hypot(event.clientX - press.x, event.clientY - press.y) > 8) press = null;
  }, true);
  document.addEventListener("pointercancel", () => { press = null; }, true);
  document.addEventListener("pointerup", event => {
    if (press && (event.pointerId !== press.pointerId || !outside(press.dialog, event))) press = null;
  }, true);
  document.addEventListener("close", event => {
    if (press?.dialog === event.target) press = null;
  }, true);
  document.addEventListener("click", event => {
    const started = press;
    press = null;
    if (!started || event.button !== 0 || !event.detail ||
        !outside(started.dialog, event)) return;
    event.preventDefault();
    event.stopPropagation();
    started.dialog.close();
  }, true);
})();
document.addEventListener("click", (event) => {
  const menu = byId("model-menu");
  if (menu.open && !menu.contains(event.target)) menu.open = false;
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (narrowScreen.matches) toggleSessions(false);
    byId("model-menu").open = false;
    if (!document.querySelector("dialog[open]") && compactInspector.matches && contextPanelOpen) {
      setContextPanel(false, true);
    }
  }
  if (event.key === "Tab" && narrowScreen.matches && layout.classList.contains("sessions-open")) {
    const controls = [...byId("session-sidebar").querySelectorAll('button:not(:disabled), input')];
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
});
for (const button of document.querySelectorAll("[data-prompt]")) {
  button.addEventListener("click", () => { prompt.value = button.dataset.prompt; resizePrompt(); prompt.focus(); });
}

function requestId() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
}

function advanceCursor(next) {
  if (!next) return;
  const [epoch, raw] = next.split(":", 2);
  const [currentEpoch, currentRaw] = cursor.split(":", 2);
  if (!cursor || epoch !== currentEpoch || Number(raw) > Number(currentRaw)) cursor = next;
}

function isNewCursor(next, previous = cursor) {
  if (!next) return false;
  if (!previous) return true;
  const [epoch, raw] = next.split(":", 2);
  const [currentEpoch, currentRaw] = previous.split(":", 2);
  return epoch !== currentEpoch || Number(raw) > Number(currentRaw);
}

async function jsonRequest(path, method = "GET", body = undefined, requestOptions = {}) {
  const epoch = authEpoch;
  const options = { method, credentials: "same-origin", headers: {} };
  if (requestOptions.signal) options.signal = requestOptions.signal;
  if (clientId) options.headers["X-Klaude-Client"] = clientId;
  if (method !== "GET" && latest && path !== "/api/v1/auth/logout") {
    options.headers["X-Klaude-Session"] = latest.session_id;
  }
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.headers["X-Klaude-CSRF"] = csrf;
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error?.message || `HTTP ${response.status}`);
    error.status = response.status;
    error.authEpoch = epoch;
    throw error;
  }
  return data;
}

async function controlledRequest(path, body, includeControlEpoch = true) {
  const sessionId = latest?.session_id;
  const epoch = authEpoch;
  const checkContext = (state = latest) => {
    if (!authenticated || epoch !== authEpoch || !sessionId ||
        latest?.session_id !== sessionId || state?.session_id !== sessionId) {
      const error = new Error("Session changed; try the action again");
      error.authEpoch = epoch;
      throw error;
    }
  };
  // Acquire only for an explicit action. Watching, polling and focusing a tab
  // never take control away from another client. Refresh control independently
  // of the rendered snapshot so a question's draft stays intact.
  for (let attempt = 0; attempt < 2; attempt++) {
    const state = await jsonRequest("/api/v1/session");
    checkContext(state);
    let controlEpoch = state.control_epoch;
    if (controlEpoch > 0 && !state.has_control) {
      try {
        const claim = await jsonRequest("/api/v1/control/claim", "POST", {
          request_id: requestId(), expected_epoch: controlEpoch,
        });
        controlEpoch = claim.control_epoch;
      } catch (error) {
        // Only retry acquisition; an action with an uncertain outcome is never
        // automatically repeated.
        if (error.status === 409 && attempt === 0) continue;
        throw error;
      }
    }
    checkContext();
    return jsonRequest(path, "POST", includeControlEpoch ?
      { ...body, control_epoch: controlEpoch } : body);
  }
}

function showError(error) {
  if (error.authEpoch !== undefined && error.authEpoch !== authEpoch) return;
  if (error.status === 401) { showLocalAccess(); return; }
  notice.textContent = error.message || String(error);
}

async function finishStartup() {
  if (document.documentElement.dataset.startup !== "loading") return;
  await window.KlaudeStartup?.complete();
  const screen = byId("app-startup"), shell = document.querySelector(".shell");
  shell.inert = false;
  shell.removeAttribute("aria-hidden");
  document.documentElement.dataset.startup = "ready";
  document.dispatchEvent(new Event("klaude-startup-ready"));
  if (!screen) return;
  screen.setAttribute("aria-hidden", "true");
  // A short exit transition, never a minimum loading delay. The timeout also
  // handles reduced motion, a background tab, or a cancelled transition.
  screen.addEventListener("transitionend", () => { screen.hidden = true; }, { once: true });
  if (systemMotion.matches || document.documentElement.dataset.motion === "reduced") screen.hidden = true;
  else setTimeout(() => { screen.hidden = true; }, 200);
}

function showLocalAccess(signedOut = false) {
  authEpoch += 1;
  authenticated = false;
  document.dispatchEvent(new Event("klaude-auth-reset"));
  byId("change-password").reset();
  byId("login-password").value = "";
  byId("account-shortcut").hidden = true;
  csrf = "";
  clientId = "";
  latest = null;
  chatSubmission = null; renderChatSendStatus();
  renderAgentActivity(null);
  linkedMessage = null;
  pendingIntent = null;
  pendingRuntimeChoice = null;
  pendingSessionChoice = null;
  messages.replaceChildren();
  activity.replaceChildren();
  byId("activity-feed").replaceChildren();
  if (stream) stream.close();
  stream = null;
  clearInterval(pollTimer);
  layout.hidden = true;
  layout.inert = true;
  byId("local-access").hidden = false;
  const passwordLogin = loginMethod === "password";
  byId("access-title").textContent = signedOut ? "Signed out" :
    passwordLogin ? "Sign in to Klaude" : "Connect this browser";
  byId("access-message").textContent = passwordLogin ? "Welcome back to your local workspace." :
    "Open /settings web in Klaude and select Open Web UI to connect this browser.";
  byId("account-login").hidden = !passwordLogin;
  byId("login-help").hidden = !passwordLogin;
  byId("access-retry").hidden = passwordLogin;
  byId("logout").disabled = true;
  byId("sessions-toggle").disabled = true;
  byId("inspector-toggle").disabled = true;
  setConnection(false, "Not connected");
  finishStartup();
}

function addMessage(role, content, id, streaming = false) {
  if (window.ChatMarkdown) {
    const article = ChatMarkdown.create(role, content, id, streaming);
    ChatMarkdown.metadata?.(article, { onAction: performMessageAction, sessionId: latest?.session_id });
    messages.append(article);
    return article;
  }
  // An older still-running host may not yet serve the new Markdown assets.
  const article = document.createElement("article");
  article.className = `message ${role}`;
  article.dataset.id = id;
  const heading = document.createElement("div");
  heading.className = "who";
  heading.textContent = role === "user" ? "You" : "Klaude";
  const text = document.createElement("pre");
  text.textContent = content;
  article.append(heading, text);
  messages.append(article);
  return article;
}

function updateMessage(article, content, streaming = false) {
  if (window.ChatMarkdown) ChatMarkdown.update(article, content, streaming);
  else if (article.querySelector("pre").textContent !== content) article.querySelector("pre").textContent = content;
}

function addActivity(label) {
  const row = document.createElement("li");
  row.textContent = label.slice(0, 200);
  activity.prepend(row);
  byId("activity-feed").prepend(row.cloneNode(true));
  byId("activity-empty").hidden = true;
  byId("inspector-empty").hidden = true;
  while (activity.children.length > 80) activity.lastChild.remove();
  while (byId("activity-feed").children.length > 80) byId("activity-feed").lastChild.remove();
}

function renderAgentActivity(value) {
  const panel = byId("agent-activity");
  const running = Boolean(value?.turn_id && value.lifecycle === "running" && value.label !== "Needs input");
  const marker = panel.querySelector(".activity-dot, .material-loading");
  if (running && window.MaterialLoading && !marker.classList.contains("material-loading")) {
    marker.replaceWith(MaterialLoading.create({ size: "medium" }));
  } else if (!running && marker.classList.contains("material-loading")) {
    const dot = document.createElement("span");
    dot.className = "activity-dot"; dot.setAttribute("aria-hidden", "true");
    marker.replaceWith(dot);
  }
  if (!value?.turn_id) {
    panel.hidden = true;
    panel.open = false;
    panel.dataset.turn = "";
    byId("agent-activity-timeline").replaceChildren();
    delete byId("agent-activity-timeline").dataset.signature;
    placeChatResponseStatus();
    return;
  }
  if (panel.dataset.turn !== value.turn_id) {
    panel.open = false;
    panel.dataset.turn = value.turn_id;
    byId("agent-activity-timeline").replaceChildren();
    delete byId("agent-activity-timeline").dataset.signature;
  }
  panel.hidden = false;
  panel.dataset.running = String(running);
  const label = value.label || ({ cancelled: "Cancelled", interrupted: "Interrupted" }[value.lifecycle]) || "Waiting";
  panel.dataset.error = String(label === "Error");
  if (byId("agent-activity-label").textContent !== label) byId("agent-activity-label").textContent = label;
  byId("agent-activity-note").textContent = value.recoverable ? "Tool failed · agent may continue" :
    value.active_count > 1 ? `${value.active_count} operations active` : "";
  if (value.timeline) {
    const list = byId("agent-activity-timeline");
    const signature = JSON.stringify(value.timeline);
    if (list.dataset.signature !== signature) {
      list.dataset.signature = signature;
      list.replaceChildren(...value.timeline.map((item) => {
        const row = document.createElement("li");
        const action = ({ "tool.requested": "Requested", "tool.started": "Started",
          "tool.finished": "Finished", "approval.required": "Approval requested",
          "approval.resolved": "Approval resolved", "user_input.required": "Question asked",
          "user_input.resolved": "Question resolved", "turn.completed": "Task completed",
          "turn.failed": "Task failed", "turn.partial": "Task incomplete",
          "turn.cancelled": "Cancelled", "turn.interrupted": "Interrupted",
          "activity.changed": "Activity" })[item.kind] || "Activity";
        row.textContent = [action, item.tool, item.status, item.label].filter(Boolean).join(" · ");
        return row;
      }));
    }
  }
  placeChatResponseStatus();
}

// Response feedback belongs to the conversation, immediately before the answer.
// Park the hidden nodes outside the log so an empty conversation stays empty,
// while retaining the same live regions and animation through snapshots/SSE.
function placeChatResponseStatus() {
  scheduleChatScrollControl();
  const status = byId("chat-send-status"), panel = byId("agent-activity");
  const nearBottom = nearLatestMessage();
  const sendingNew = chatSubmission?.epoch === authEpoch &&
    chatSubmission.session === latest?.session_id && chatSubmission.disposition === "start" &&
    !latest.active_turn_id;
  panel.hidden = !panel.dataset.turn || sendingNew;
  chatResponseStatus.hidden = status.hidden && panel.hidden;
  if (chatResponseStatus.hidden) {
    if (chatResponseStatus.parentElement === messages) messages.parentElement.append(chatResponseStatus);
    return;
  }
  const anchor = sendingNew ? messages.querySelector(":scope > .message:last-of-type") :
    [...messages.children].reverse().find(element => element.classList.contains("user"));
  if (anchor) {
    if (anchor.nextElementSibling !== chatResponseStatus) anchor.after(chatResponseStatus);
  } else if (messages.firstElementChild !== chatResponseStatus) messages.prepend(chatResponseStatus);
  byId("welcome").hidden = true;
  if (nearBottom) messages.scrollTop = messages.scrollHeight;
}

function renderChatSendStatus() {
  const status = byId("chat-send-status");
  const sending = chatSubmission?.epoch === authEpoch && chatSubmission.session === latest?.session_id;
  const hasActivity = latest?.active_turn_id && latest.activity?.turn_id === latest.active_turn_id;
  const needsInput = latest?.approvals?.length || latest?.questions?.length;
  const label = authenticated && latest ? sending ? chatSubmission.label :
    latest.active_turn_id && !hasActivity && !needsInput ? "Generating response…" : "" : "";
  status.hidden = !label;
  if (!label) { status.replaceChildren(); placeChatResponseStatus(); return; }
  if (!status.hasChildNodes()) {
    if (window.MaterialLoading) status.append(MaterialLoading.create({ size: "medium" }));
    const text = document.createElement("span");
    text.className = "chat-send-label"; status.append(text);
  }
  status.querySelector(".chat-send-label").textContent = label;
  placeChatResponseStatus();
}

function renderApprovals(items) {
  const signature = JSON.stringify(items);
  if (approvalSignature === signature) return;
  approvalSignature = signature;
  approvals.replaceChildren();
  for (const item of items) {
    const card = document.createElement("div");
    card.className = "approval";
    const title = document.createElement("strong");
    title.textContent = `Allow ${item.tool}?`;
    const detail = document.createElement("p");
    detail.textContent = item.detail || "No arguments";
    card.append(title, detail);
    for (const [label, decision] of [["Allow once", "allow_once"], ["Deny", "deny"]]) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = decision === "deny" ? "secondary" : "";
      button.textContent = label;
      button.addEventListener("click", async () => {
        for (const sibling of card.querySelectorAll("button")) sibling.disabled = true;
        try {
          await controlledRequest(`/api/v1/interactions/${encodeURIComponent(item.id)}/decision`,
            { request_id: requestId(), decision });
          await snapshot();
        } catch (error) { approvalSignature = ""; showError(error); await snapshot().catch(showError); }
      });
      card.append(button);
    }
    approvals.append(card);
  }
}

function renderQuestions(items) {
  const signature = JSON.stringify(items);
  if (questionSignature === signature) return;
  questionSignature = signature;
  questions.replaceChildren();
  for (const item of items) {
    const card = document.createElement("form");
    card.className = "question";
    const title = document.createElement("strong");
    title.textContent = item.header || "Klaude asks";
    const question = document.createElement("p");
    question.textContent = item.question;
    const choices = document.createElement("div");
    choices.className = "field-row";
    const input = document.createElement("input");
    input.maxLength = 1000;
    input.placeholder = "Your answer";
    input.setAttribute("aria-label", item.question);
    const submit = document.createElement("button");
    submit.type = "submit";
    submit.textContent = "Answer";
    card.append(title, question);
    for (const option of item.options || []) {
      const choice = document.createElement("button");
      choice.type = "button";
      choice.className = "secondary";
      choice.textContent = option;
      choice.addEventListener("click", () => { input.value = option; card.requestSubmit(); });
      choices.append(choice);
    }
    choices.append(input, submit);
    card.append(choices);
    card.addEventListener("submit", async (event) => {
      event.preventDefault();
      const answer = input.value.trim().replace(/\s+/g, " ");
      if (!answer) return;
      for (const button of card.querySelectorAll("button")) button.disabled = true;
      try {
        await controlledRequest(`/api/v1/interactions/${encodeURIComponent(item.id)}/answer`,
          { request_id: requestId(), answer });
        await snapshot();
      } catch (error) { questionSignature = ""; showError(error); await snapshot().catch(showError); }
    });
    questions.append(card);
  }
}

function renderQueue(items) {
  queue.replaceChildren();
  queue.hidden = !items.length;
  if (!items.length) return;
  const heading = document.createElement("strong");
  heading.textContent = "Queued work";
  queue.append(heading);
  for (const item of items) {
    const row = document.createElement("p");
    row.textContent = item.mine ? `${item.state}: ${item.text}` : `${item.state}: another client's message`;
    queue.append(row);
  }
}

let snapshotRequest = 0, snapshotApplied = 0;
async function snapshot() {
  const request = ++snapshotRequest;
  const epoch = authEpoch;
  const finish = latest ? () => {} : beginChatLoading();
  let data;
  try { data = await jsonRequest("/api/v1/session"); }
  finally { finish(); }
  if (!authenticated || epoch !== authEpoch || request < snapshotApplied) return;
  snapshotApplied = request;
  const previousModel = latest?.model;
  const previousSession = latest?.session_id;
  if (latest && latest.session_id !== data.session_id) {
    document.dispatchEvent(new Event("klaude-chat-session-changed"));
    linkedMessage = null;
    if (stream) stream.close();
    stream = null;
    cursor = "";
    eventCursor = "";
    pendingIntent = null;
    chatSubmission = null;
    pendingRuntimeChoice = null;
    activity.replaceChildren();
    byId("activity-feed").replaceChildren();
    byId("activity-empty").hidden = false;
    byId("inspector-empty").hidden = false;
    refreshSessions().catch(showError);
  }
  if (cursor && data.cursor) {
    const [epoch, raw] = data.cursor.split(":", 2);
    const [currentEpoch, currentRaw] = cursor.split(":", 2);
    if (epoch === currentEpoch && Number(raw) < Number(currentRaw)) return;
  }
  latest = data;
  renderAgentActivity(data.activity);
  renderChatSendStatus();
  window.refreshLibraryCapabilities?.();
  window.BrowserManagement?.capabilitiesChanged();
  window.BrowserMedia?.capabilitiesChanged();
  window.BrowserModelsUI?.capabilitiesChanged();
  if (!window.BrowserMedia) {
    byId("media-settings-status").textContent = "Restart the Web UI host and reload to load model and image settings.";
    byId("image-settings-status").textContent = byId("media-settings-status").textContent;
  }
  setConnection(true, "Connected");
  if (previousModel !== data.model || previousSession !== data.session_id) {
    byId("model-choice").value = "";
  }
  if (stream && cursor && data.cursor &&
      data.cursor.split(":", 1)[0] !== cursor.split(":", 1)[0]) {
    stream.close();
    stream = null;
    eventCursor = "";
  }
  advanceCursor(data.cursor);
  byId("model").textContent = data.requires_model_selection ? "Choose a model" : data.model;
  byId("mode-toggle").title = data.mode === "thinking" ?
    "Turn Thinking off" : "Turn Thinking on";
  byId("mode-toggle").disabled = Boolean(data.active_turn_id) ||
    Boolean(data.queue?.length) || Boolean(data.requires_model_selection);
  byId("mode-toggle").setAttribute("aria-pressed", String(data.mode === "thinking"));
  byId("session").textContent = `Session ${data.session_id.slice(0, 8)}`;
  byId("session").title = data.session_id;
  byId("state").textContent = data.state;
  byId("plan-toggle").title = data.plan_mode ? "Disable Plan mode" : "Enable Plan mode";
  byId("plan-toggle").setAttribute("aria-pressed", String(data.plan_mode));
  byId("plan-toggle").disabled = Boolean(data.active_turn_id);
  byId("tool-policy").textContent = data.tools;
  byId("enable-edits").hidden = data.tools === "file edits enabled";
  byId("enable-edits").disabled = Boolean(data.active_turn_id);
  byId("new-session").disabled = Boolean(data.active_turn_id) ||
    Boolean(data.queue?.length);
  renderModelOptions();
  const busy = Boolean(data.active_turn_id);
  byId("cancel").hidden = !busy;
  byId("steer").hidden = !busy;
  byId("send").setAttribute("aria-label", busy ? "Queue message" : "Send message");
  byId("send").title = busy ? "Queue message" : "Send message";
  byId("send").disabled = pending || Boolean(data.requires_model_selection);
  if (window.ChatAttachmentsUI) window.ChatAttachmentsUI.refresh();
  else {
    byId("attach-file").disabled = true;
    byId("attach-file").title = "Restart Web UI, then reload to enable attachments";
    byId("chat-attachment-status").textContent =
      "Attachments could not load. Restart Web UI, then reload this page.";
    byId("chat-attachment-status").hidden = false;
  }
  byId("steer").disabled = pending;
  byId("cancel").disabled = pending;
  const nearBottom = nearLatestMessage();
  renderApprovals(data.approvals || []);
  renderQuestions(data.questions || []);
  renderQueue(data.queue || []);
  const visibleMessages = [...data.messages];
  const earlierLink = linkedMessage?.sessionId === data.session_id &&
    !visibleMessages.some(message => message.id === linkedMessage.message.id);
  if (earlierLink) visibleMessages.unshift(linkedMessage.message);
  if (data.partial) visibleMessages.push({ role: "assistant", content: data.partial, id: "partial" });
  // Promote the streamed article in place so completion preserves selection,
  // code scroll positions and focused Copy controls.
  const partialArticle = messages.querySelector('[data-id="partial"]');
  if (partialArticle && window.ChatMarkdown) {
    const source = ChatMarkdown.source(partialArticle);
    const completed = [...data.messages].reverse().find((message) =>
      message.role === "assistant" && message.content.startsWith(source) &&
      ![...messages.children].some((element) => element.dataset.id === message.id));
    if (source && completed) partialArticle.dataset.id = completed.id;
  }
  const retained = new Set(visibleMessages.map((message) => message.id));
  if (earlierLink) retained.add("linked-message-gap");
  for (const element of [...messages.children]) {
    if (element !== chatResponseStatus && !retained.has(element.dataset.id)) element.remove();
  }
  for (const message of visibleMessages) {
    const existing = [...messages.children].find((element) => element.dataset.id === message.id);
    const streaming = message.id === "partial" && busy;
    const article = existing || addMessage(message.role, message.content, message.id, streaming);
    if (earlierLink && message.id === linkedMessage.message.id &&
        messages.firstElementChild !== article) messages.prepend(article);
    if (existing) updateMessage(existing, message.content, streaming);
    window.ChatMarkdown?.metadata?.(article, {
      createdAt: message.created_at,
      sessionId: data.session_id,
      canAct: data.message_actions === true && !busy && !data.queue?.length && !pending &&
        message.id.startsWith("stored:"),
    });
    window.ChatAttachmentsUI?.renderMessage(article, message, data.session_id);
  }
  if (earlierLink && !messages.querySelector('[data-id="linked-message-gap"]')) {
    const gap = document.createElement("p");
    gap.dataset.id = "linked-message-gap";
    gap.className = "message-history-gap muted";
    gap.textContent = "Later messages omitted · Latest messages below";
    messages.firstElementChild.after(gap);
  }
  byId("welcome").hidden = visibleMessages.length > 0 || busy;
  placeChatResponseStatus();
  renderSessionList();
  if (nearBottom) messages.scrollTop = messages.scrollHeight;
  document.dispatchEvent(new CustomEvent("klaude-snapshot", { detail: data }));
  connect();
}

function renderModelOptions() {
  if (!latest) return;
  const select = byId("model-choice");
  const selected = select.value;
  const currentModel = latest.model_providers ? latest.model_ref : latest.model;
  select.replaceChildren();
  const choices = localModels.some((item) => item.id === currentModel) ?
    localModels : [{ id: currentModel, name: latest.model }, ...localModels];
  for (const item of choices) {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.name;
    select.append(option);
  }
  select.value = choices.some((item) => item.id === selected) ? selected : currentModel;
  const locked = runtimeChoiceInFlight || Boolean(latest.active_turn_id) || Boolean(latest.queue?.length);
  select.disabled = locked || !localModels.length;
  byId("apply-model").disabled = locked || !localModels.length ||
    select.value === currentModel && !latest.requires_model_selection;
  byId("model-connection-choice").disabled = locked;
  const levels = (latest.effort_levels || []).filter(value => value !== "off");
  byId("effort-label").hidden = byId("effort-choice").hidden = !latest.model_providers || levels.length < 2;
  byId("effort-choice").replaceChildren(...levels.map(level => {
    const option = document.createElement("option"); option.value = level; option.textContent = level[0].toUpperCase() + level.slice(1); return option;
  }));
  byId("effort-choice").value = levels.includes(latest.effort) ? latest.effort : levels.includes("medium") ? "medium" : levels[0] || "";
  byId("effort-choice").disabled = locked;
  window.BrowserModelsUI?.render();
}

async function refreshModels() {
  const load = ++modelsLoad;
  const epoch = authEpoch;
  const finish = beginLoading(byId("model-status"), { kind: "text", count: 1, preserve: localModels.length > 0, label: "Loading models…" });
  try {
    const providers = Boolean(latest?.model_providers);
    byId("model-connection-label").hidden = byId("model-connection-choice").hidden = !providers;
    let path = "/api/v1/models/local";
    if (providers) {
      const inventory = await jsonRequest("/api/v1/models/connections");
      if (load !== modelsLoad || epoch !== authEpoch || !authenticated) return;
      const connection = byId("model-connection-choice"), previous = connection.value;
      connection.replaceChildren(...inventory.connections.map(item => {
        const option = document.createElement("option"); option.value = item.id;
        option.textContent = `${item.name} · ${item.source}`; option.disabled = !item.enabled; return option;
      }));
      const preferred = [previous, latest.model_connection, inventory.connections.find(item => item.enabled && item.backend === "ollama" && item.source === "Local")?.id, inventory.connections.find(item => item.enabled)?.id];
      connection.value = preferred.find(id => inventory.connections.some(item => item.id === id && item.enabled)) || "";
      if (!connection.value) throw new Error("No enabled model connection. Add one in Klaude's Model settings.");
      path = `/api/v1/models/catalog?connection=${encodeURIComponent(connection.value)}`;
    }
    const data = await jsonRequest(path);
    if (load !== modelsLoad || epoch !== authEpoch || !authenticated) return;
    localModels = data.models;
    byId("model-status").textContent = localModels.length ?
      `${localModels.length} ${providers ? "" : "local "}model${localModels.length === 1 ? "" : "s"}` :
      "No models found in this connection";
  } catch (error) {
    if (load !== modelsLoad || epoch !== authEpoch || !authenticated) return;
    byId("model-status").textContent = error.message;
  }
  finally { finish(); }
  renderModelOptions();
}

async function chooseRuntime(kind, value, { onError = showError } = {}) {
  if (!latest || runtimeChoiceInFlight || latest.active_turn_id || latest.queue?.length) return false;
  runtimeChoiceInFlight = true;
  const epoch = authEpoch;
  const effort = byId("effort-choice").value;
  renderModelOptions();
  const key = `${latest.session_id}\u0000${kind}\u0000${value}\u0000${effort}`;
  if (!pendingRuntimeChoice || pendingRuntimeChoice.key !== key) {
    pendingRuntimeChoice = { key, requestId: requestId() };
  }
  try {
    const configured = kind === "model" && latest.model_providers;
    await controlledRequest(`/api/v1/session/${configured ? "configured-model" : kind}`, {
      request_id: pendingRuntimeChoice.requestId,
      [configured ? "model_ref" : kind === "model" ? "model_id" : "mode"]: value,
      ...(kind === "mode" && latest.model_providers ? { effort: value === "thinking" ? effort || "medium" : null } : {}),
      expected_revision: latest.settings_revision,
    });
    if (epoch !== authEpoch) return false;
    pendingRuntimeChoice = null;
    await snapshot();
    await refreshSessions();
    return true;
  } catch (error) {
    if (epoch === authEpoch) { onError(error); await snapshot().catch(onError); }
    return false;
  } finally {
    if (epoch === authEpoch) { runtimeChoiceInFlight = false; renderModelOptions(); }
  }
}
byId("model-choice").addEventListener("change", renderModelOptions);
byId("apply-model").addEventListener("click", () =>
  chooseRuntime("model", byId("model-choice").value));
byId("refresh-models").addEventListener("click", refreshModels);
byId("model-connection-choice").addEventListener("change", () => { localModels = []; byId("model-choice").replaceChildren(); refreshModels(); });
byId("effort-choice").addEventListener("change", () => chooseRuntime("mode", "thinking"));
byId("mode-toggle").addEventListener("click", () =>
  chooseRuntime("mode", latest?.mode === "thinking" ? "standard" : "thinking"));

async function refreshSessions() {
  const load = ++sessionsLoad;
  const epoch = authEpoch;
  const finish = beginLoading(byId("session-list"), { kind: "rows", count: 5, preserve: sessionsLoaded, label: "Loading conversations…" });
  if (!sessionsLoaded) byId("session-empty").hidden = true;
  try {
    const data = await jsonRequest(`/api/v1/sessions?archived=${byId("archived-sessions").getAttribute("aria-pressed") === "true"}`);
    if (load !== sessionsLoad || epoch !== authEpoch || !authenticated) return;
    sessions = data.sessions;
    sessionsLoaded = true;
    renderSessionList();
  } finally { finish(); }
}

function renderSessionList() {
  const list = byId("session-list");
  if (!sessionsLoaded && loadingStates.has(list)) return;
  list.replaceChildren();
  const filter = byId("session-search").value.trim().toLowerCase();
  for (const item of sessions) {
    if (filter && !`${item.title || ""} ${item.preview || ""} ${item.session_id}`.toLowerCase().includes(filter)) continue;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = item.title || item.preview || item.session_id.slice(0, 12);
    button.title = item.resumable ? item.preview : "Requires this session's model and mode";
    button.className = item.session_id === latest?.session_id ? "selected" : "";
    button.disabled = !item.resumable || item.session_id === latest?.session_id ||
      Boolean(latest?.active_turn_id) || Boolean(latest?.queue?.length);
    button.addEventListener("click", () => switchSession(item.session_id));
    list.append(window.BrowserManagement?.sessionRow(item, button) || button);
  }
  byId("session-empty").hidden = Boolean(list.children.length);
  byId("session-empty").textContent = filter ? "No matching conversations." :
    byId("archived-sessions").getAttribute("aria-pressed") === "true" ? "No archived conversations." :
      "Your conversations will appear here.";
}
byId("session-search").addEventListener("input", renderSessionList);
byId("archived-sessions").addEventListener("click", () => {
  const button = byId("archived-sessions");
  const archived = button.getAttribute("aria-pressed") !== "true";
  button.setAttribute("aria-pressed", String(archived));
  button.title = archived ? "Show saved conversations" : "Show archived conversations";
  byId("session-list").setAttribute("aria-label", archived ? "Archived conversations" : "Saved conversations");
  sessions = [];
  sessionsLoaded = false;
  byId("session-list").replaceChildren();
  refreshSessions().catch(showError);
});

async function switchSession(sessionId, { fromLink = false } = {}) {
  if (!latest || latest.active_turn_id || latest.queue?.length) return false;
  const key = `${latest.session_id}\u0000${sessionId}`;
  if (!pendingSessionChoice || pendingSessionChoice.key !== key) {
    pendingSessionChoice = { key, requestId: requestId() };
  }
  const finish = beginChatLoading();
  try {
    await controlledRequest("/api/v1/session/select", {
      request_id: pendingSessionChoice.requestId,
      expected_session_id: latest.session_id,
      session_id: sessionId,
    });
    pendingSessionChoice = null;
    if (narrowScreen.matches) toggleSessions(false);
    await snapshot();
    finish();
    if (!fromLink) rememberLinkedSession();
    await refreshSessions();
    return true;
  } catch (error) { showError(error); await snapshot().catch(showError); return false; }
  finally { finish(); }
}
byId("new-session").addEventListener("click", () => switchSession(""));
byId("refresh-sessions").addEventListener("click", () => refreshSessions().catch(showError));

async function performMessageAction(action, article) {
  if (!latest || pending || latest.active_turn_id || latest.queue?.length) return;
  const messageId = article.dataset.id;
  const message = latest.messages.find(message => message.id === messageId) ||
    (linkedMessage?.sessionId === latest.session_id ? linkedMessage.message : null);
  if (message?.id !== messageId || message.role !== "assistant") return;
  pending = true;
  const finish = beginChatLoading();
  try {
    await controlledRequest("/api/v1/messages/action", {
      request_id: requestId(), source_session_id: latest.session_id,
      message_id: messageId, action,
    });
    await snapshot();
    finish();
    rememberLinkedSession();
    await refreshSessions();
  } catch (error) { showError(error); }
  finally { finish(); pending = false; snapshot().catch(showError); }
}

function connect() {
  if (!authenticated || stream || !cursor) return;
  if (!eventCursor) eventCursor = cursor;
  const source = new EventSource(`/api/v1/events?after=${encodeURIComponent(eventCursor)}`);
  stream = source;
  source.onmessage = (event) => {
    if (stream !== source) return;
    let item;
    try { item = JSON.parse(event.data); } catch { return; }
    if (!isNewCursor(item.cursor, eventCursor)) return;
    eventCursor = item.cursor;
    const changesState = isNewCursor(item.cursor);
    advanceCursor(item.cursor);
    if (changesState && item.current_activity) renderAgentActivity(item.current_activity);
    if (item.kind === "stream.reset_required") {
      stream.close();
      stream = null;
      eventCursor = "";
      snapshot().catch(showError);
      return;
    }
    if (item.kind === "message.delta" && changesState) {
      let partial = messages.querySelector('[data-id="partial"]');
      if (!partial) partial = addMessage("assistant", "", "partial", true);
      const nearBottom = nearLatestMessage();
      byId("welcome").hidden = true;
      if (window.ChatMarkdown) ChatMarkdown.append(partial, item.text || "");
      else partial.querySelector("pre").textContent += item.text || "";
      if (nearBottom) messages.scrollTop = messages.scrollHeight;
    }
    if (item.kind === "tool.requested") addActivity(`Requested ${item.tool || "tool"}`);
    if (item.kind === "tool.started") addActivity(`Running ${item.tool || "tool"}`);
    if (item.kind === "tool.finished") {
      addActivity(`${item.tool || "Tool"}: ${item.status || (item.executed ? "finished" : "not run")}`);
    }
    if (item.kind.startsWith("turn.")) addActivity(item.kind.replace(".", " "));
    if (["tool.requested", "tool.started", "tool.finished", "activity.changed",
      "approval.required", "approval.resolved", "user_input.required",
      "user_input.resolved", "queue.changed", "session.state", "settings.changed",
      "workspace.changed",
      "message.completed", "turn.completed", "turn.partial", "turn.failed",
      "turn.cancelled", "turn.interrupted"].includes(item.kind) && changesState) {
      snapshot().catch(showError);
    }
  };
  source.onerror = () => {
    if (stream !== source) return;
    stream.close();
    stream = null;
    setConnection(false, "Reconnecting");
    setTimeout(() => snapshot().catch(showError), 1200);
  };
}

async function sendMessage(disposition) {
  const text = prompt.value.trim();
  if (!text || pending || !latest) return;
  const attachments = window.ChatAttachmentsUI?.ids() || [];
  if (window.ChatAttachmentsUI?.preparing() || attachments.length && latest.active_turn_id) return;
  const activeTurn = latest.active_turn_id;
  const effectiveDisposition = disposition === "steer" ? "steer" :
    activeTurn ? "queue" : "start";
  const intentKey = `${effectiveDisposition}\u0000${activeTurn || ""}\u0000${text}\u0000${attachments.join(",")}`;
  if (!pendingIntent || pendingIntent.key !== intentKey) {
    pendingIntent = { key: intentKey, requestId: requestId() };
  }
  pending = true;
  notice.textContent = "";
  const submission = { epoch: authEpoch, session: latest.session_id,
    disposition: effectiveDisposition,
    label: effectiveDisposition === "queue" ? "Queueing message…" :
      effectiveDisposition === "steer" ? "Sending instruction…" : "Sending…" };
  chatSubmission = submission;
  byId("send").disabled = true;
  window.ChatAttachmentsUI?.refresh();
  renderChatSendStatus();
  try {
    if (disposition === "steer") {
      if (!latest.active_turn_id) return;
      await controlledRequest(`/api/v1/turns/${encodeURIComponent(latest.active_turn_id)}/steer`,
        { request_id: pendingIntent.requestId, text });
    } else {
      await jsonRequest("/api/v1/turns", "POST", {
        request_id: pendingIntent.requestId, text,
        disposition: effectiveDisposition,
        ...(attachments.length ? { attachments } : {}),
      });
    }
    if (submission.epoch !== authEpoch || submission.session !== latest?.session_id) return;
    pendingIntent = null;
    prompt.value = "";
    prompt.style.height = "auto";
    window.ChatAttachmentsUI?.clear();
    await snapshot();
  } catch (error) { showError(error); }
  finally {
    pending = false;
    if (chatSubmission === submission) chatSubmission = null;
    renderChatSendStatus();
    if (window.ChatAttachmentsUI) window.ChatAttachmentsUI.refresh();
    else byId("send").disabled = false;
    snapshot().catch(showError);
  }
}

byId("composer").addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage("send");
});
byId("steer").addEventListener("click", () => sendMessage("steer"));
byId("cancel").addEventListener("click", async () => {
  if (!latest?.active_turn_id || pending) return;
  pending = true;
  try {
    await controlledRequest(`/api/v1/turns/${encodeURIComponent(latest.active_turn_id)}/cancel`,
      { request_id: requestId() });
    await snapshot();
  } catch (error) { showError(error); }
  finally { pending = false; snapshot().catch(showError); }
});
byId("plan-toggle").addEventListener("click", async () => {
  if (!latest || latest.active_turn_id) return;
  try {
    await controlledRequest("/api/v1/session/plan-mode", {
      request_id: requestId(), enabled: !latest.plan_mode,
      expected_revision: latest.settings_revision,
    });
    await snapshot();
  } catch (error) { showError(error); await snapshot().catch(showError); }
});

// Keep navigation local to this tab; store only allowlisted page identifiers.
function readNavigationChoice(key, choices, fallback) {
  try {
    const saved = sessionStorage.getItem(`klaude.webui.navigation.v1.${key}`);
    if (choices.includes(saved)) return saved;
  } catch { /* Navigation still works when browser storage is unavailable. */ }
  return fallback;
}
function saveNavigationChoice(key, value) {
  try { sessionStorage.setItem(`klaude.webui.navigation.v1.${key}`, value); }
  catch { /* Browser storage is optional. */ }
}

const settingsSections = ["account", "theme", "agent", "models", "memory"];
let settingsSection = readNavigationChoice("settings-section", [...settingsSections, "images"], "account");
let settingsSectionGeneration = 0;
function showSettingsSection(section, { restore = false, focus = false } = {}) {
  if (section === "images") {
    section = "models";
    if (authenticated && currentView === "settings") {
      const url = new URL(location.href);
      if (url.searchParams.get("settings") === "images") {
        url.searchParams.set("settings", "models");
        history.replaceState(history.state, "", url.pathname + url.search + url.hash);
      }
    }
  }
  if (!settingsSections.includes(section) || section === "account" && loginMethod !== "password")
    section = loginMethod === "password" ? "account" : "theme";
  const changed = settingsSection !== section;
  if (changed) settingsSectionGeneration += 1;
  if (changed && settingsSection === "account") {
    byId("change-password").reset();
    byId("password-status").textContent = "";
  }
  const tabs = [...byId("settings-sections").querySelectorAll("[data-settings]")];
  const selected = tabs.find(tab => tab.dataset.settings === section);
  const panelFocus = document.activeElement.closest("#settings-view [role='tabpanel']");
  for (const tab of tabs) {
    const active = tab === selected;
    tab.hidden = tab.dataset.settings === "account" && loginMethod !== "password";
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
    byId(tab.getAttribute("aria-controls")).hidden = !active;
  }
  settingsSection = section;
  saveNavigationChoice("settings-section", section);
  if (changed) byId("settings-view").scrollTop = 0;
  if (currentView === "settings") {
    if (focus || panelFocus?.hidden) selected.focus({ preventScroll: true });
    selected.scrollIntoView({ block: "nearest", inline: "nearest" });
  }
  if (authenticated && currentView === "settings" && changed && !restore) {
    const url = new URL(location.href);
    url.searchParams.set("view", "settings");
    url.searchParams.set("settings", section);
    history.pushState(history.state, "", url.pathname + url.search + url.hash);
  }
}
for (const tab of byId("settings-sections").querySelectorAll("[data-settings]")) {
  tab.addEventListener("click", () => showSettingsSection(tab.dataset.settings));
}
const desktopSettings = matchMedia("(min-width: 851px)");
window.SettingsActions = (() => {
  const dock = byId("settings-action-dock"), view = byId("settings-view");
  const entries = [], phone = matchMedia("(max-width: 560px)");
  let frame = 0, focusFrame = 0, previousClearance = 0;
  const property = (node, name, value) => {
    if (node.style.getPropertyValue(name) !== value) node.style.setProperty(name, value);
  };
  function refresh() {
    cancelAnimationFrame(frame); frame = 0;
    const mobile = !desktopSettings.matches && authenticated && currentView === "settings";
    const active = mobile ? entries.find(entry => !entry.panel.hidden && !entry.bar.hidden) : null;
    for (const entry of entries) {
      if (entry === active) {
        if (entry.bar.parentElement !== dock) dock.append(entry.bar);
      } else if (entry.bar.parentNode !== entry.anchor.parentNode) entry.anchor.after(entry.bar);
    }
    dock.hidden = !active;
    const tabs = byId("settings-sections");
    property(view, "--settings-navigation-size", `${Math.ceil(tabs.getBoundingClientRect().height)}px`);
    const viewport = window.visualViewport;
    const visibleBottom = viewport && viewport.scale === 1 ? viewport.offsetTop + viewport.height : innerHeight;
    const viewportInset = Math.max(0, innerHeight - visibleBottom);
    const rail = document.querySelector(".rail").getBoundingClientRect();
    const navigationInset = phone.matches ? Math.max(0, innerHeight - rail.top) : 0;
    const keyboardInset = mobile ? Math.max(0, viewportInset - navigationInset) : 0;
    property(view, "--settings-keyboard-inset", `${Math.ceil(keyboardInset)}px`);
    if (active) {
      const bottom = Math.ceil(Math.max(viewportInset, navigationInset));
      const main = byId("main-content").getBoundingClientRect();
      property(dock, "inset-inline-start", phone.matches ? "0px" : `${Math.max(0, main.left)}px`);
      property(dock, "inset-inline-end", phone.matches ? "0px" : `${Math.max(0, innerWidth - main.right)}px`);
      property(dock, "bottom", `${bottom}px`);
      property(dock, "--settings-dock-safe-bottom", bottom ? "0px" : "env(safe-area-inset-bottom, 0px)");
      property(dock, "--settings-viewport-size", `${Math.max(0, visibleBottom - (viewport?.offsetTop || 0))}px`);
    }
    const height = active ? Math.ceil(dock.getBoundingClientRect().height) : 0;
    property(view, "--settings-actions-size", `${height}px`);
    const clearance = height + keyboardInset;
    const focused = document.activeElement;
    if (mobile && clearance !== previousClearance && view.contains(focused) && focused.matches("input, textarea, select")) {
      // Let the new padding and native scroll anchoring settle before checking
      // the focused field against the keyboard/dock's actual visible boundary.
      cancelAnimationFrame(focusFrame);
      focusFrame = requestAnimationFrame(() => {
        if (document.activeElement !== focused || view.hidden || desktopSettings.matches) return;
        const field = focused.getBoundingClientRect(), bounds = view.getBoundingClientRect();
        const top = Math.max(bounds.top, tabs.getBoundingClientRect().bottom, viewport?.offsetTop || 0) + 8;
        const bottom = Math.min(bounds.bottom, active ? dock.getBoundingClientRect().top : visibleBottom) - 8;
        if (field.bottom > bottom) view.scrollTop += field.bottom - bottom;
        else if (field.top < top) view.scrollTop -= top - field.top;
      });
    }
    previousClearance = clearance;
  }
  function schedule() { if (!frame) frame = requestAnimationFrame(refresh); }
  const visibility = new MutationObserver(schedule);
  visibility.observe(view, { attributes: true, attributeFilter: ["hidden"] });
  function register(bar, panel) {
    const anchor = document.createComment("Settings action bar home"); bar.before(anchor);
    entries.push({ bar, panel, anchor });
    visibility.observe(bar, { attributes: true, attributeFilter: ["hidden"] });
    visibility.observe(panel, { attributes: true, attributeFilter: ["hidden"] });
    schedule();
  }
  const size = new ResizeObserver(schedule);
  for (const node of [dock, byId("settings-sections"), document.querySelector(".rail"), byId("main-content")]) size.observe(node, { box: "border-box" });
  for (const event of ["resize", "scroll"]) window.visualViewport?.addEventListener(event, schedule);
  window.addEventListener("resize", schedule);
  desktopSettings.addEventListener("change", refresh);
  document.addEventListener("klaude-view", refresh);
  document.addEventListener("klaude-auth-reset", schedule);
  register(byId("theme-save-bar"), byId("theme-settings"));
  return { register, refresh };
})();
function updateSettingsOrientation() {
  byId("settings-sections").setAttribute("aria-orientation", desktopSettings.matches ? "vertical" : "horizontal");
  if (currentView === "settings") showSettingsSection(settingsSection, { restore: true });
}
desktopSettings.addEventListener("change", updateSettingsOrientation);
desktopSettings.addEventListener("change", updateThemeActions);
updateSettingsOrientation();
byId("settings-sections").addEventListener("keydown", event => {
  const tabs = [...byId("settings-sections").querySelectorAll("[role='tab']")].filter(tab => !tab.hidden);
  const index = tabs.indexOf(document.activeElement);
  if (index < 0) return;
  const forward = desktopSettings.matches ? "ArrowDown" : "ArrowRight";
  const backward = desktopSettings.matches ? "ArrowUp" : "ArrowLeft";
  const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 :
    event.key === forward ? (index + 1) % tabs.length :
      event.key === backward ? (index - 1 + tabs.length) % tabs.length : null;
  if (next !== null) {
    event.preventDefault();
    showSettingsSection(tabs[next].dataset.settings, { focus: true });
  }
});

function showView(view, { restore = false, section = null } = {}) {
  if (!viewNames.includes(view)) view = "chat";
  const changed = currentView !== view;
  const previousSettingsSection = settingsSection;
  if (currentView === "settings" && view !== "settings") {
    settingsSectionGeneration += 1;
    applyAppearance(appearance, true);
    byId("change-password").reset();
    byId("password-status").textContent = "";
  }
  for (const name of viewNames) {
    byId(`${name}-view`).hidden = name !== view;
    byId(`nav-${name}`).classList.toggle("selected", name === view);
    if (name === view) byId(`nav-${name}`).setAttribute("aria-current", "page");
    else byId(`nav-${name}`).removeAttribute("aria-current");
  }
  const target = byId(`${view}-view`);
  if (view !== currentView && !systemMotion.matches && document.documentElement.dataset.motion !== "reduced") {
    target.getAnimations().forEach((animation) => animation.cancel());
    target.animate([{ opacity: .3, transform: "translateY(8px)" }, { opacity: 1, transform: "translateY(0)" }],
      { duration: 400, easing: "cubic-bezier(.05,.7,.1,1)" });
  }
  currentView = view;
  if (view === "settings") showSettingsSection(section ||
    (restore ? new URLSearchParams(location.search).get("settings") : null) || settingsSection, { restore: true });
  const more = byId("nav-more"), moreMenu = byId("navigation-more");
  const secondary = ["models", "activity", "settings"].includes(view);
  more.classList.toggle("selected", secondary);
  if (secondary) more.setAttribute("aria-current", "page"); else more.removeAttribute("aria-current");
  more.setAttribute("aria-label", secondary ? `More navigation · ${{ models: "Models", activity: "Activity", settings: "Settings" }[view]}` : "More navigation");
  for (const button of moreMenu.querySelectorAll("[data-app-view]")) {
    if (button.dataset.appView === view) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  if (moreMenu.matches(":popover-open")) moreMenu.hidePopover();
  if (authenticated && !restore && (changed || view === "settings" && previousSettingsSection !== settingsSection)) {
    const url = new URL(location.href);
    for (const key of [...url.searchParams.keys()])
      if (["library", "integrations", "settings", "sources-page"].includes(key) || key.startsWith("files-") || key.startsWith("knowledge-") || key.startsWith("skills-")) url.searchParams.delete(key);
    url.searchParams.set("view", view);
    if (view === "settings") url.searchParams.set("settings", settingsSection);
    if (view !== "chat") { url.searchParams.delete("session"); url.searchParams.delete("message"); }
    history.pushState(history.state, "", url.pathname + url.search + url.hash);
  }
  saveNavigationChoice("page", view);
  if (view === "workspace" && authenticated) workspaceRead(workspaceOperation);
  document.dispatchEvent(new CustomEvent("klaude-view", { detail: view }));
  if (narrowScreen.matches) toggleSessions(false);
}
byId("nav-chat").addEventListener("click", () => showView("chat"));
byId("nav-workspace").addEventListener("click", () => showView("workspace"));
byId("nav-models").addEventListener("click", () => showView("models"));
byId("nav-activity").addEventListener("click", () => showView("activity"));
byId("nav-settings").addEventListener("click", () => showView("settings"));
const navigationMore = byId("navigation-more");
const navigationRail = document.querySelector(".rail");
// Only the bar's intrinsic size is observed; browser viewport/keyboard sizing
// and focused-input scrolling retain their native behavior.
const navigationSizeObserver = new ResizeObserver(() => {
  if (!window.matchMedia("(max-width: 560px)").matches || !navigationRail.getClientRects().length) return;
  const style = getComputedStyle(navigationRail);
  const safeBottom = Math.max(0, parseFloat(style.paddingBottom) - parseFloat(style.paddingTop));
  document.documentElement.style.setProperty("--mobile-navigation-size",
    `${Math.ceil(navigationRail.getBoundingClientRect().height - safeBottom)}px`);
});
navigationSizeObserver.observe(navigationRail, { box: "border-box" });
const closeNavigationMore = () => {
  if (navigationMore.matches(":popover-open")) navigationMore.hidePopover();
};
document.addEventListener("klaude-auth-reset", closeNavigationMore);
window.matchMedia("(max-width: 560px)").addEventListener("change", (event) => {
  if (!event.matches) closeNavigationMore();
});
navigationMore.addEventListener("toggle", (event) => {
  byId("nav-more").setAttribute("aria-expanded", String(event.newState === "open"));
  if (event.newState === "open") navigationMore.querySelector("button").focus();
});
for (const button of navigationMore.querySelectorAll("[data-app-view]")) {
  button.prepend(byId(`nav-${button.dataset.appView}`).querySelector("svg").cloneNode(true));
  button.addEventListener("click", () => {
    showView(button.dataset.appView);
    const heading = byId(`${button.dataset.appView}-view`).querySelector("h1");
    heading.setAttribute("tabindex", "-1");
    heading.focus({ preventScroll: true });
  });
}
navigationMore.addEventListener("keydown", (event) => {
  const buttons = [...navigationMore.querySelectorAll("button")];
  const index = buttons.indexOf(document.activeElement);
  const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 :
    event.key === "ArrowDown" ? (index + 1) % buttons.length :
      event.key === "ArrowUp" ? (index - 1 + buttons.length) % buttons.length : null;
  if (next !== null) { event.preventDefault(); buttons[next].focus(); }
  if (event.key === "Escape") { event.preventDefault(); navigationMore.hidePopover(); byId("nav-more").focus(); }
});
byId("account-shortcut").addEventListener("click", () => {
  showView("settings", { section: "account" });
  byId("account-heading").focus({ preventScroll: true });
});
byId("enable-edits").addEventListener("click", async () => {
  if (!latest) return;
  const button = byId("enable-edits");
  button.disabled = true;
  try {
    const result = await controlledRequest("/api/v1/workspace/activate-edits", {
      request_id: requestId(), expected_revision: latest.workspace_revision,
      acknowledge: true,
    }, false);
    byId("edit-status").textContent = result.status;
    await snapshot();
  } catch (error) { byId("edit-status").textContent = error.message; }
  finally { button.disabled = false; }
});

async function workspaceRead(operation) {
  workspaceOperation = operation;
  const path = byId("workspace-path").value || ".";
  const result = byId("workspace-result");
  result.querySelector(".loading-error")?.remove();
  const load = ++workspaceLoad;
  const epoch = authEpoch;
  const sessionId = latest?.session_id;
  const params = new URLSearchParams();
  if (["files", "file", "search"].includes(operation)) params.set("path", path);
  if (operation === "search") params.set("pattern", byId("search-pattern").value);
  const key = `${operation}?${params}`;
  const finish = beginLoading(result, { kind: "code", count: 1, preserve: result.dataset.contentKey === key, label: "Loading workspace…" });
  try {
    const data = await jsonRequest(`/api/v1/workspace/${operation}?${params}`);
    if (load !== workspaceLoad || epoch !== authEpoch || !authenticated || sessionId !== latest?.session_id) return;
    result.replaceChildren();
    const title = document.createElement("h2");
    title.textContent = operation === "files" ? `Files in ${path}` :
      operation === "file" ? path : operation === "search" ? "Search results" :
        operation === "status" ? "Changes" : "Diff";
    const text = document.createElement("pre");
    text.textContent = data.text;
    result.append(title, text);
    window.KlaudeExpressive?.workspace(result, data.text, operation, path);
    result.dataset.contentKey = key;
  } catch (error) {
    if (load !== workspaceLoad || epoch !== authEpoch || !authenticated || sessionId !== latest?.session_id) return;
    if (error.status === 401) showLocalAccess();
    else if (result.dataset.contentKey === key && result.querySelector("pre, .workspace-files")) {
      const status = document.createElement("p");
      status.className = "loading-error muted";
      status.textContent = error.message;
      result.prepend(status);
    } else result.textContent = error.message;
  } finally { finish(); }
}
for (const [id, operation] of [["browse", "files"], ["read-file", "file"],
  ["search", "search"], ["git-status", "status"], ["git-diff", "diff"]]) {
  byId(id).addEventListener("click", () => workspaceRead(operation));
}

byId("logout").addEventListener("click", async () => {
  if (!authenticated) { showLocalAccess(); return; }
  try {
    await jsonRequest("/api/v1/auth/logout", "POST", {});
    showLocalAccess(true);
  } catch (error) { showError(error); }
});

function highlightLinkedMessage(article) {
  clearTimeout(messageHighlightTimer);
  for (const previous of messages.querySelectorAll(".linked-message"))
    previous.classList.remove("linked-message", "linked-message-faded");
  article.classList.add("linked-message");
  messageHighlightTimer = setTimeout(() => {
    messageHighlightTimer = null;
    if (article.isConnected) article.classList.add("linked-message-faded");
  }, 3000);
}

function rememberLinkedSession(messageId = null) {
  const url = new URL(location.href);
  if (!url.searchParams.has("session") || !latest) return;
  url.searchParams.set("session", latest.session_id);
  if (messageId) url.searchParams.set("message", messageId);
  else url.searchParams.delete("message");
  url.hash = "";
  history.replaceState({ ...history.state, klaudeLinkedSession: latest.session_id,
    klaudeLinkedMessage: messageId }, "", url.pathname + url.search);
}

async function openConversationLink() {
  const parameters = new URLSearchParams(location.search);
  const target = parameters.get("session");
  const messageId = parameters.get("message");
  if (target === null && messageId === null) return;
  if (!/^[a-f0-9]{32}$/.test(target || "") || parameters.getAll("session").length !== 1 ||
      parameters.getAll("message").length > 1 || messageId !== null &&
      (!/^stored:[1-9]\d{0,18}$/.test(messageId) ||
        BigInt(messageId.slice(7)) > 9223372036854775807n)) {
    notice.textContent = "This conversation link is invalid.";
    return;
  }
  const openedBefore = history.state?.klaudeLinkedSession === target &&
    (history.state?.klaudeLinkedMessage || null) === messageId;
  const previousView = currentView;
  if (target !== latest?.session_id) {
    if (latest?.active_turn_id || latest?.queue?.length) {
      notice.textContent = "Finish the current reply before opening this conversation.";
      return;
    }
    if (!await switchSession(target, { fromLink: true })) return;
  }
  if (!openedBefore && currentView === previousView) showView("chat");
  if (messageId !== null) {
    if (!latest.messages.some(message => message.id === messageId)) {
      const epoch = authEpoch;
      const query = new URLSearchParams({ session: target, message: messageId });
      const finish = beginChatLoading();
      try {
        const data = await jsonRequest(`/api/v1/session?${query}`);
        if (!authenticated || epoch !== authEpoch || latest?.session_id !== target ||
            data.session_id !== target) return;
        if (data.linked_message?.id !== messageId ||
            !["user", "assistant"].includes(data.linked_message.role) ||
            typeof data.linked_message.content !== "string") {
          notice.textContent = "This message is unavailable in the current conversation history.";
          return;
        }
        linkedMessage = { sessionId: target, message: data.linked_message };
        await snapshot();
      } catch (error) { showError(error); return; }
      finally { finish(); }
    }
    if (currentView === "chat") {
      const article = [...messages.children].find(element => element.dataset.id === messageId);
      if (!article) return;
      highlightLinkedMessage(article);
      article.tabIndex = -1;
      const focusMessage = () => {
        if (!article.isConnected || currentView !== "chat") return;
        article.focus({ preventScroll: true });
        article.scrollIntoView({ block: "start", inline: "nearest", behavior: "instant" });
      };
      if (document.documentElement.dataset.startup === "loading")
        document.addEventListener("klaude-startup-ready", focusMessage, { once: true });
      else focusMessage();
    }
  }
  rememberLinkedSession(messageId);
}

async function initialize() {
  const epoch = ++authEpoch;
  byId("access-status").textContent = "";
  const method = await jsonRequest("/api/v1/auth/method");
  if (epoch !== authEpoch) return;
  loginMethod = method.method;
  byId("settings-tab-account").hidden = loginMethod !== "password";
  const code = location.hash.slice(1);
  if (code && loginMethod === "bootstrap") {
    history.replaceState(null, "", location.pathname + location.search);
    const response = await fetch("/api/v1/auth/exchange", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
    const data = await response.json();
    if (epoch !== authEpoch) return;
    if (!response.ok) {
      showLocalAccess();
      byId("access-status").textContent = "This browser link expired or was already used. Open a fresh link from Klaude.";
      return;
    }
    csrf = data.csrf;
  } else {
    if (code) history.replaceState(null, "", location.pathname + location.search);
    const auth = await jsonRequest("/api/v1/auth");
    if (epoch !== authEpoch) return;
    csrf = auth.csrf;
    const username = auth.username || "admin";
    byId("account-initial").textContent = Array.from(username)[0].toLocaleUpperCase();
    byId("account-shortcut").setAttribute("aria-label", `Account settings for ${username}`);
  }
  const client = await jsonRequest("/api/v1/clients", "POST", {});
  if (epoch !== authEpoch) return;
  clientId = client.client_id;
  authenticated = true;
  const pageQuery = new URLSearchParams(location.search);
  showView(pageQuery.get("library") === "knowledge" || ["skills", "knowledge"].includes(pageQuery.get("integrations")) ?
    "integrations" : ["files", "outputs"].includes(pageQuery.get("library")) ?
      "library" : viewNames.includes(pageQuery.get("view")) ? pageQuery.get("view") : readNavigationChoice("page", viewNames, "chat"), { restore: true });
  layout.hidden = false;
  layout.inert = false;
  byId("local-access").hidden = true;
  byId("account-shortcut").hidden = loginMethod !== "password";
  byId("logout").disabled = false;
  byId("sessions-toggle").disabled = false;
  byId("inspector-toggle").disabled = false;
  await snapshot();
  await openConversationLink();
  await refreshSessions();
  await refreshModels();
  if (epoch !== authEpoch || !authenticated) return;
  clearInterval(pollTimer);
  pollTimer = setInterval(() => { if (authenticated && !stream) snapshot().catch(showError); }, 2000);
  finishStartup();
}
function initializationFailed(error) {
  if (error.authEpoch !== undefined && error.authEpoch !== authEpoch) return;
  showLocalAccess();
  if (error.status !== 401) byId("access-status").textContent = error.message || String(error);
}
byId("access-retry").addEventListener("click", () => initialize().catch(initializationFailed));
byId("account-login").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = byId("login-submit");
  if (button.disabled) return;
  button.disabled = true;
  byId("access-status").textContent = "";
  try {
    const result = await jsonRequest("/api/v1/auth/login", "POST", {
      username: byId("login-username").value, password: byId("login-password").value,
    });
    csrf = result.csrf;
    byId("login-password").value = "";
    await initialize();
  } catch (error) { byId("access-status").textContent = error.message || String(error); }
  finally { button.disabled = false; }
});
byId("change-password").addEventListener("submit", async (event) => {
  event.preventDefault();
  const replacement = byId("new-password").value;
  if (replacement !== byId("confirm-password").value) {
    byId("password-status").textContent = "The new passwords do not match.";
    return;
  }
  const button = byId("password-submit");
  if (button.disabled) return;
  button.disabled = true;
  byId("password-status").textContent = "";
  try {
    await jsonRequest("/api/v1/auth/password", "POST", {
      current_password: byId("current-password").value, new_password: replacement,
    });
    byId("change-password").reset();
    showLocalAccess(true);
    byId("access-status").textContent = "Password changed. Sign in with your new password.";
  } catch (error) {
    if (error.status === 401) showLocalAccess();
    else byId("password-status").textContent = error.message || String(error);
  } finally { button.disabled = false; }
});
window.addEventListener("hashchange", () => {
  if (location.hash.length > 1) initialize().catch(initializationFailed);
});
initialize().catch(initializationFailed);
