import requests
import os
import time

# API端点 - 可通过环境变量配置
api_url = os.getenv("OCR_API_URL", "http://localhost:8000/ocr/")
pdf_path = os.getenv("TEST_PDF_PATH", "test_input.pdf")
output_path = os.getenv("OUTPUT_PDF_PATH", "test_output.pdf")

# 检查输入文件是否存在
if not os.path.exists(pdf_path):
    print(f"错误: 输入文件不存在: {pdf_path}")
    print("请设置环境变量 TEST_PDF_PATH 指向一个有效的PDF文件")
    exit(1)

# 准备文件和参数
files = {"pdf_file": open(pdf_path, "rb")}
data = {
    "language": "eng+chi_sim",
    "deskew": "true",
    "optimize": "1"
}

print(f"开始处理文件: {pdf_path}")
print(f"文件大小: {os.path.getsize(pdf_path)/1024/1024:.2f} MB")
print(f"API URL: {api_url}")
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
except Exception as e:
    print(f"请求失败: {str(e)}")
finally:
    # 确保关闭文件
    files["pdf_file"].close()