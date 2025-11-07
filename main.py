# pip install openai tdqm

from openai import OpenAI, APIError, APITimeoutError
from tqdm import tqdm
import os, time, sys, traceback

# UTF-8 출력 깨짐 방지
sys.stdout.reconfigure(encoding='utf-8')

# 🔑 OpenAI API 키 입력
client = OpenAI(api_key="")

# 폴더 설정
input_dir = "converted"
output_dir = "transcripts"
os.makedirs(output_dir, exist_ok=True)

# 파일 목록
files = [f for f in os.listdir(input_dir) if f.lower().endswith(".wav")]
if not files:
    print("⚠️ converted 폴더에 wav 파일이 없습니다.")
    exit()

print(f"🎧 총 {len(files)}개 파일 전사+번역 시작...\n")

# 진행률 표시
for idx, fname in enumerate(tqdm(files, desc="진행률"), start=1):
    wav_path = os.path.join(input_dir, fname)
    out_path = os.path.join(output_dir, fname.replace(".wav", "_ko.txt"))

    print(f"\n[{idx}/{len(files)}] ▶ {fname} 처리 시작")
    print(f"   파일 크기: {os.path.getsize(wav_path)/1024/1024:.2f} MB")

    if os.path.exists(out_path):
        print(f"⏩ 이미 완료됨: {fname}")
        continue

    # ========================
    # 1️⃣ Whisper 전사 단계
    # ========================
    success = False
    for attempt in range(2):  # 최대 2회 시도
        try:
            print(f"   [Whisper] API 호출 시도 {attempt+1}/2 ...")
            start = time.time()
            with open(wav_path, "rb") as f:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    timeout=180   # 3분 제한
                )
            elapsed = time.time() - start
            print(f"   [Whisper] 완료 ⏱ {elapsed:.1f}초")
            text = transcript.text.strip()
            success = True
            break
        except (APIError, APITimeoutError, Exception) as e:
            print(f"   ⚠️ Whisper 오류 ({type(e).__name__}): {e}")
            traceback.print_exc()
            time.sleep(5)

    if not success:
        print(f"❌ Whisper 완전 실패: {fname}")
        continue

    # ========================
    # 2️⃣ 번역 단계
    # ========================
    try:
        print("   [GPT 번역] 시작 ...")
        prompt = f"다음 문장을 자연스럽고 정확한 한국어로 번역해줘:\n\n{text[:4000]}"
        start = time.time()
        translation = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            timeout=120
        )
        elapsed = time.time() - start
        print(f"   [GPT 번역] 완료 ⏱ {elapsed:.1f}초")

        translated = translation.choices[0].message.content.strip()

        # ========================
        # 3️⃣ 결과 저장
        # ========================
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("【원문 Transcript】\n")
            f.write(text + "\n\n【한국어 번역】\n")
            f.write(translated)

        print(f"✅ 완료: {fname}")

    except (APIError, APITimeoutError, Exception) as e:
        print(f"❌ 번역 실패: {fname} ({type(e).__name__})")
        traceback.print_exc()
        continue

    # Whisper 과부하 방지
    time.sleep(1)

print("\n🎉 모든 파일 전사+번역 완료!")
