import requests
import os
import time

# API端点
api_url = "https://blueskyxn-ocrmypdf-hfs.hf.space/ocr/"
pdf_path = r"F:\Download\20250401-113339.pdf"
output_path = r"F:\Download\ocr_result_python.pdf"

# 准备文件和参数
files = {"pdf_file": open(pdf_path, "rb")}
data = {
    "language": "eng+chi_sim",
    "deskew": "true",
    "optimize": "1"
}

print(f"开始处理文件: {pdf_path}")
print(f"文件大小: {os.path.getsize(pdf_path)/1024/1024:.2f} MB")
start_time = time.time()

try:
    # 发送请求
    print("正在发送请求到OCR API...")
    response = requests.post(api_url, files=files, data=data)
    
    # 处理响应
    if response.status_code == 200:
        # 保存处理后的PDF
        with open(output_path, "wb") as f:
            f.write(response.content)
        print(f"PDF处理成功！耗时: {time.time() - start_time:.2f}秒")
        print(f"结果已保存到: {output_path}")
    else:
        print(f"处理失败! 状态码: {response.status_code}")
        try:
            error_details = response.json()
            print(f"错误详情: {error_details}")
        except:
            print(f"响应内容: {response.text[:500]}...")
finally:
    # 确保关闭文件
    files["pdf_file"].close()