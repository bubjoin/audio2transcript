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
# ⚙️ ffmpeg 없이 MP3 조각 자르기
# ======================================
def slice_mp3(file_path, start_sec, end_sec, out_path):
    """ffmpeg 없이 mutagen만 사용해 MP3 조각 자르기"""
    try:
        audio = MP3(file_path)
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


# ======== 번역 관련 헬퍼 함수 ========
_alpha_re = re.compile(r'[A-Za-z]')

def needs_translation(line: str) -> bool:
    """영문자가 하나라도 있으면 번역 대상"""
    return bool(_alpha_re.search(line))

def chunk_text(s: str, max_len: int = 1500):
    """너무 긴 줄을 안전 길이로 쪼개 타임아웃 방지"""
    chunks = []
    start = 0
    n = len(s)
    while start < n:
        end = min(start + max_len, n)
        if end < n:
            m = re.search(r'\s', s[start:end][::-1])
            if m and m.start() < 40:
                end = end - m.start()
        chunks.append(s[start:end])
        start = end
    return chunks

def translate_chunk(text_chunk: str, timeout_sec: int = 120, retry: int = 2) -> str:
    """GPT 번역 (안정적 재시도 포함)"""
    last_err = None
    for attempt in range(retry + 1):
        try:
            prompt = (
                "다음 영어 문장을 자연스럽고 정확한 한국어로 번역해줘.\n"
                "다른 설명, 인용부호, 머리말 없이 번역문만 출력:\n\n"
                f"{text_chunk}"
            )
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                timeout=timeout_sec
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            last_err = e
            time.sleep(1.0 + attempt)
    print(f"⚠️ 번역 실패 지속: {type(last_err).__name__} - {last_err}")
    return text_chunk
# ===============================


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
    # 🌐 GPT 번역 (문맥 보존형)
    # ======================================
    print("   [GPT 번역] 시작 ...")

    # 문장 분리: 종결부호 (.!? ) 로만 분리 → 쉼표/and 제거
    sentences = re.split(r'(?<=[.!?])\s+', full_text.strip())
    processed_lines = []

    for i, sentence in enumerate(sentences, start=1):
        line = sentence.strip()
        if not line:
            continue

        # 영문자 포함 시 무조건 번역
        if not needs_translation(line):
            processed_lines.append(line)
            continue

        # 긴 문장은 내부 청크로 나눠서 번역 후 결합
        chunks = chunk_text(line, max_len=1500)
        translated_chunks = [translate_chunk(c, timeout_sec=120, retry=2) for c in chunks]
        merged_kor = " ".join(translated_chunks).strip()

        processed_lines.append(f"{line}\n    → {merged_kor}")

    # 사후 스윕: 혹시 번역 빠진 줄 재번역
    final_lines = []
    for line in processed_lines:
        if '→' in line:
            final_lines.append(line)
            continue
        if needs_translation(line):
            chunks = chunk_text(line, max_len=1000)
            translated_chunks = [translate_chunk(c, timeout_sec=120, retry=2) for c in chunks]
            merged_kor = " ".join(translated_chunks).strip()
            final_lines.append(f"{line}\n    → {merged_kor}")
        else:
            final_lines.append(line)

    # 💾 파일 저장
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"🎧 파일명: {fname}\n")
        f.write("──────────────────────────────\n")
        f.write("\n".join(final_lines))
        f.write("\n──────────────────────────────\n")

    print(f"✅ 완료: {fname}")
    time.sleep(1)

print("\n🎉 모든 MP3 파일 전사+번역 완료!")
