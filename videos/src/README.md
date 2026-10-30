# AI 교육 광고 시안 영상 원본

- ad2a.html: 시안 A 끝까지 같이 하는 일들 (29.5초, 가로, lib/toss.css 사용, 소리는 sound.py)
- ad2b.html: 시안 B 같이 굴러가는 길 (29.5초, 가로, lib/toss.css 사용, 소리는 sound.py)
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

결과는 out 폴더에 MP4로 생깁니다. render.py 로 뽑은 영상에는 소리가 없고, 소리는 아래 순서로 입힙니다.

## 소리 입히기 (ad2a, ad2b)

1. 파이썬 패키지 numpy, scipy, pillow 를 설치합니다(pip install numpy scipy pillow).
2. Mixkit 무료 음원을 받아 sound_assets 폴더에 넣습니다. 음원 파일은 재배포가 안 돼 저장소에 올리지 않았습니다.
   - sound_assets/music/173.mp3: Better Times are Coming (Alejandro Magaña), https://assets.mixkit.co/music/173/173.mp3
   - sound_assets/music/474.mp3: What About Action? (Diego Nava), https://assets.mixkit.co/music/474/474.mp3
   - sound_assets/sfx/번호.wav: https://assets.mixkit.co/active_storage/sfx/번호/번호.wav
     번호: 1109 1120 1393 1464 1489 1492 168 1714 1993 2070 2182 2352 2357 2569 2585 2625 2655 2867 3005 3062 3141 772 790
3. render.py 로 out/ad2a_h.mp4, out/ad2b_h.mp4 를 먼저 만든 뒤 python sound.py ad2a ad2b 를 실행합니다.
4. 결과는 out/ad2a_h_sound.mp4, out/ad2b_h_sound.mp4 이고, 음량은 -14 LUFS로, 최고 음량은 -1 dB 아래로 맞춰집니다. qc/sound_ad2a.png 에 파형과 편집 지점이 그려집니다.

음악을 자르는 지점, 효과음의 시각(초)과 역할(크기 기준)은 sound.py 의 build_a, build_b 안에 그대로 적혀 있습니다. 단계 넘김과 정거장 체크 소리는 두 곡에 쓰인 음(G#, B, C#, D#, F#)으로 직접 만듭니다.

Mixkit 무료 라이선스(음악, 효과음)는 상업 광고, 유튜브, 온라인 광고에 쓸 수 있고 출처 표기가 필요 없습니다(https://mixkit.co/license/).

입체 아이콘(assets/fluent)은 Microsoft Fluent Emoji 이며 MIT 라이선스입니다(assets/fluent/LICENSE.txt).
