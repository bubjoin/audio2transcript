import os

# 합칠 파일 범위
start = 1
end = 204

# 파일들이 있는 폴더 (같은 폴더라면 ".")
folder = "./transcripts"

# 출력 파일명
output_file = "merged_output.txt"

separator = "\n=======\n\n"   # 빈 줄 → ======= → 빈 줄

with open(output_file, "w", encoding="utf-8") as outfile:
    for i in range(start, end + 1):
        filename = os.path.join(folder, f"{i}_ko.txt")
        
        if not os.path.isfile(filename):
            print(f"파일 없음: {filename}, 건너뜀")
            continue
        
        with open(filename, "r", encoding="utf-8") as infile:
            content = infile.read().rstrip()
            outfile.write(content)
        
        # 마지막 파일 뒤에는 구분선을 넣지 않음
        if i != end:
            outfile.write(separator)

print(f"완료: {output_file} 생성됨")
