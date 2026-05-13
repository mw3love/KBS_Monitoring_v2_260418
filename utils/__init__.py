def format_duration(sec: float) -> str:
    """초를 '1시간 02분 03초' / '2분 05초' / '45초' 형식으로 변환."""
    s = int(sec)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}시간 {m:02d}분 {s:02d}초"
    if m > 0:
        return f"{m}분 {s:02d}초"
    return f"{s}초"
