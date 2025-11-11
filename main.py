# pip install openai tqdm mutagen python-dotenv

from openai import OpenAI, APIError, APITimeoutError
from tqdm import tqdm
from mutagen.mp3 import MP3
from dotenv import load_dotenv
import os, time, sys, traceback, math, re

# ✅ UTF-8 깨짐 방지
sys.stdout.reconfigure(encoding='utf-8')

# ✅ .env에서 OpenAI API 키 로드
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("❌ .env 파일에 OPENAI_API_KEY가 없습니다. .env 파일을 확인하세요.")

client = OpenAI(api_key=api_key)

input_dir = "converted"
output_dir = "transcripts"
os.makedirs(output_dir, exist_ok=True)

files = [f for f in os.listdir(input_dir) if f.lower().endswith(".mp3")]
if not files:
    print("⚠️ converted 폴더에 mp3 파일이 없습니다.")
    exit()

print(f"🎧 총 {len(files)}개 파일 전사+번역 시작...\n")


# ======================================
# 🔹 MP3 길이 읽기 및 조각 구간 계산
# ======================================
def split_mp3_positions(file_path, chunk_sec=60):
    """MP3 길이를 기준으로 1분 단위 구간 반환"""
    audio = MP3(file_path)
    length_sec = audio.info.length
    count = math.ceil(length_sec / chunk_sec)
    return [(i * chunk_sec, min((i + 1) * chunk_sec, length_sec)) for i in range(count)]


# ======================================
# ⚙️ ffmpeg 없이 MP3 조각 자르기 (핵심 수정 부분)
# ======================================
def slice_mp3(file_path, start_sec, end_sec, out_path):
    """ffmpeg 없이 mutagen만 사용해 MP3 조각 자르기"""
    try:
        audio = MP3(file_path)
        total_time = audio.info.length
        bitrate = audio.info.bitrate  # bps 단위 (예: 128000)
        bytes_per_sec = bitrate / 8   # 초당 바이트 수 계산

        start_b = int(start_sec * bytes_per_sec)
        end_b = int(end_sec * bytes_per_sec)

        with open(file_path, "rb") as f:
            header = f.read(2048)  # 헤더 확보
            f.seek(start_b)
            data = f.read(end_b - start_b)

        with open(out_path, "wb") as out:
            out.write(header)
            out.write(data)
    except Exception as e:
        print(f"⚠️ MP3 슬라이스 중 오류 발생: {e}")
        raise


# ======================================
# 🧠 메인 루프
# ======================================
for idx, fname in enumerate(tqdm(files, desc="진행률"), start=1):
    mp3_path = os.path.join(input_dir, fname)
    out_path = os.path.join(output_dir, fname.replace(".mp3", "_ko.txt"))

    print(f"\n[{idx}/{len(files)}] ▶ {fname} 처리 시작")
    print(f"   파일 크기: {os.path.getsize(mp3_path)/1024/1024:.2f} MB")

    if os.path.exists(out_path):
        print(f"⏩ 이미 완료됨: {fname}")
        continue

    positions = split_mp3_positions(mp3_path, chunk_sec=60)
    print(f"   ▶ 총 {len(positions)}개 조각으로 처리 예정")

    # 🎧 Whisper 전사
    full_text = ""
    for part_idx, (start, end) in enumerate(positions, start=1):
        print(f"   [Whisper] ({part_idx}/{len(positions)}) {start:.0f}~{end:.0f}초 ...")
        temp = f"temp_{part_idx}.mp3"
        slice_mp3(mp3_path, start, end, temp)

        success = False
        for attempt in range(2):
            try:
                with open(temp, "rb") as f:
                    print("      ⏳ Whisper 서버 전송 중...")
                    t0 = time.time()
                    transcript = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=f,
                        timeout=600
                    )
                print(f"      ✅ Whisper 완료 ({time.time()-t0:.1f}초)")
                full_text += transcript.text.strip() + "\n"
                success = True
                break
            except Exception as e:
                print(f"      ⚠️ Whisper 오류: {e}")
                traceback.print_exc()
                time.sleep(3)
        os.remove(temp)
        if not success:
            print(f"      ❌ Whisper 실패 (조각 {part_idx})")
            continue

    if not full_text.strip():
        print(f"❌ Whisper 완전 실패: {fname}")
        continue

    # ======================================
    # 🌐 GPT 번역 (영문 문장만 아래 줄에 번역 추가)
    # ======================================
    print("   [GPT 번역] 시작 ...")

    sentences = re.split(r'(?<=[.!?])\s+', full_text.strip())
    processed_lines = []

    for i, sentence in enumerate(sentences, start=1):
        # 한글 포함 여부 판단
        if re.search(r'[가-힣]', sentence):
            processed_lines.append(sentence)
            continue

        try:
            prompt = (
                f"다음 영어 문장을 자연스럽게 한국어로 번역해줘. "
                f"단, 다른 설명 없이 번역문만 출력:\n\n{sentence}"
            )
            translation = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                timeout=60
            )
            translated = translation.choices[0].message.content.strip()
            merged_line = f"{sentence}\n    → {translated}"
            processed_lines.append(merged_line)
        except Exception as e:
            print(f"⚠️ 번역 실패 ({type(e).__name__}): {e}")
            processed_lines.append(sentence)
            continue

    # 💾 파일 저장
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"🎧 파일명: {fname}\n")
        f.write("──────────────────────────────\n")
        f.write("\n".join(processed_lines))
        f.write("\n──────────────────────────────\n")

    print(f"✅ 완료: {fname}")
    time.sleep(1)

print("\n🎉 모든 MP3 파일 전사+번역 완료!")
