import cv2, numpy as np, sys
a = cv2.imread('f0.png'); b = cv2.imread('f6.png')
def analyze(x1,y1,x2,y2):
    ca = a[y1:y2,x1:x2].astype(np.float32); cb = b[y1:y2,x1:x2].astype(np.float32)
    m = np.abs(cb-ca) > 4          # detector.py: diff > still_threshold(4), BGR 채널별
    h,w = m.shape[:2]
    re = np.linspace(0,h,6,dtype=int); ce = np.linspace(0,w,6,dtype=int)
    blk = np.array([[m[re[r]:re[r+1],ce[c]:ce[c+1]].mean()*100 for c in range(5)] for r in range(5)])
    return m, blk
for name,box in (('talk',(740,752,1075,905)),('ski',(20,552,355,710))):
    m,blk = analyze(*box)
    print(name,'global %.1f'%(m.mean()*100),'max %.1f'%blk.max(),'n>=10:',(blk>=10).sum())
    print(np.round(blk,1))
