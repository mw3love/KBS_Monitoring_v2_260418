import cv2, numpy as np
im = cv2.imdecode(np.fromfile('C:/Users/KBS/Dev/KBS_Monitoring_v2_260418/docs/소개서/main.jpg', np.uint8), 1)
X0, Y0, SF = 111, 121, 1380/1920
def box(x,y,w,h): return int(X0+x*SF), int(Y0+y*SF), int(w*SF), int(h*SF)
ORANGE = (87,119,217)  # BGR of #D97757
# ── HSV: A1 (1TV ON-AIR 레벨미터) ──
x,y,w,h = box(1449,120,27,124)
crop = im[y:y+h, x:x+w]
hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
mask = cv2.inRange(hsv, np.array([40,80,60]), np.array([95,255,255]))
ratio = (mask>0).mean()*100
print('A1 ROI px', w, h, 'ratio %.1f' % ratio)
Z = 6
orig = cv2.resize(crop, None, fx=Z, fy=Z, interpolation=cv2.INTER_NEAREST)
mk = cv2.resize(cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR), None, fx=Z, fy=Z, interpolation=cv2.INTER_NEAREST)
mk[np.all(mk==255,axis=2)] = (122,220,140)   # 통과 픽셀 = 연두
mk[np.all(mk==0,axis=2)] = (28,23,26)
gap = np.full((orig.shape[0], 40, 3), (28,23,26), np.uint8)
cv2.imwrite('fig_hsv.png', np.hstack([orig, gap, mk]))
# 맥락: 1TV ON-AIR 타일 + A1·V1 감지영역 표시
cx, cy = box(1430,0,0,0)[:2]
ctx = im[Y0:Y0+int(300*SF)+60, int(X0+1420*SF):int(X0+1920*SF)].copy()
ox, oy = int(X0+1420*SF), Y0
cv2.rectangle(ctx, (x-ox,y-oy), (x-ox+w,y-oy+h), ORANGE, 2)
cv2.imwrite('fig_hsv_ctx.png', cv2.resize(ctx, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))
# ── 5×5 격자: V5 (2TV ON-AIR) ──
x,y,w,h = box(1497,819,417,214)
t = im[y:y+h, x:x+w].copy()
t = cv2.resize(t, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
H,W = t.shape[:2]
for i in range(1,5):
    cv2.line(t,(int(W*i/5),0),(int(W*i/5),H),ORANGE,2); cv2.line(t,(0,int(H*i/5)),(W,int(H*i/5)),ORANGE,2)
cv2.rectangle(t,(0,0),(W-1,H-1),ORANGE,3)
cv2.imwrite('fig_grid.png', t)
print('grid', t.shape)
