# AI 교육 광고 시안 영상 원본

- ad2a.html: 시안 A 끝까지 같이 하는 일들 (25초, 가로, lib/toss.css 사용)
- ad2b.html: 시안 B 같이 굴러가는 길 (26초, 가로, lib/toss.css 사용)
- ad1b.html: 1안 두 번째 시안, 90%에서 멈추지 마세요 (30초, 가로)
- plan1.html: 1안 실제 서비스 화면과 큰 글자 (30초)
- plan2.html: 2안 선 그림 일러스트 (24초)
- plan3.html: 3안 글자만으로 15초 (15초)

문구와 등장 시간(초)은 각 파일 아래쪽 build 안에 그대로 적혀 있습니다. 주소 끝에 ?fmt=h 를 붙이면 가로(1920x1080), ?fmt=v 를 붙이면 세로(1080x1920) 화면입니다.

## 다시 뽑기

1. 글꼴 파일을 assets 폴더에 복사합니다. 홈페이지 프론트 저장소의 public/renewal/assets/pretendard.woff2, public/fonts/S-CoreDream-6Bold.woff, S-CoreDream-8Heavy.woff, S-CoreDream-9Black.woff
2. 파이썬 Playwright(pip install playwright pillow), 설치된 구글 크롬, FFmpeg 를 준비합니다.
3. 장면 확인: python render.py stills plan1 h 1,5,12
4. 영상 만들기: python render.py blur 5 ad2a:h (움직임 번짐 포함, 5는 한 프레임당 찍는 장 수) 또는 python render.py video plan1:h plan1:v

결과는 out 폴더에 MP4로 생깁니다. 소리는 들어 있지 않습니다.

입체 아이콘(assets/fluent)은 Microsoft Fluent Emoji 이며 MIT 라이선스입니다(assets/fluent/LICENSE.txt).
