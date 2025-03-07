import os
import json
import gradio as gr
import subprocess
import pandas as pd
from pathlib import Path
import shutil
import time
import re

# 創建工作目錄
WORKSPACE_DIR = "olmocr_workspace"
os.makedirs(WORKSPACE_DIR, exist_ok=True)

def modify_html_for_better_display(html_content):
    """修改HTML以便在Gradio中更好地顯示"""
    if not html_content:
        return html_content
    
    # 增加容器寬度
    html_content = html_content.replace('<div class="container">', 
                                       '<div class="container" style="max-width: 100%; width: 100%;">')
    
    # 增加文本大小
    html_content = html_content.replace('<style>', 
                                       '<style>\nbody {font-size: 16px;}\n.text-content {font-size: 16px; line-height: 1.5;}\n')
    
    # 調整圖像和文本部分的大小比例
    html_content = html_content.replace('<div class="row">', 
                                       '<div class="row" style="display: flex; flex-wrap: wrap;">')
    html_content = html_content.replace('<div class="col-md-6">', 
                                       '<div class="col-md-6" style="flex: 0 0 50%; max-width: 50%; padding: 15px;">')
    
    # 增加頁面之間的間距
    html_content = html_content.replace('<div class="page">', 
                                       '<div class="page" style="margin-bottom: 30px; border-bottom: 1px solid #ccc; padding-bottom: 20px;">')
    
    # 增加圖像大小
    html_content = re.sub(r'<img([^>]*)style="([^"]*)"', 
                         r'<img\1style="max-width: 100%; height: auto; \2"', 
                         html_content)
    
    # 添加縮放控制
    zoom_controls = """
    <div style="position: fixed; bottom: 20px; right: 20px; background: #fff; padding: 10px; border-radius: 5px; box-shadow: 0 0 10px rgba(0,0,0,0.2); z-index: 1000;">
        <button onclick="document.body.style.zoom = parseFloat(document.body.style.zoom || 1) + 0.1;" style="margin-right: 5px;">放大</button>
        <button onclick="document.body.style.zoom = parseFloat(document.body.style.zoom || 1) - 0.1;">縮小</button>
    </div>
    """
    html_content = html_content.replace('</body>', f'{zoom_controls}</body>')
    
    return html_content

def process_pdf(pdf_file):
    """處理PDF文件並返回結果"""
    if pdf_file is None:
        return "請上傳PDF文件", "", None, None
    
    # 創建一個唯一的工作目錄
    timestamp = int(time.time())
    work_dir = os.path.join(WORKSPACE_DIR, f"job_{timestamp}")
    os.makedirs(work_dir, exist_ok=True)
    
    # 複製PDF文件
    pdf_path = os.path.join(work_dir, "input.pdf")
    shutil.copy(pdf_file, pdf_path)
    
    # 構建命令並執行
    cmd = ["python", "-m", "olmocr.pipeline", work_dir, "--pdfs", pdf_path]
    
    try:
        # 執行命令，等待完成
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        
        # 命令輸出
        log_text = process.stdout
        
        # 檢查結果目錄
        results_dir = os.path.join(work_dir, "results")
        if not os.path.exists(results_dir):
            return f"處理完成，但未生成結果目錄\n\n日志輸出:\n{log_text}", "", None, None
        
        # 查找輸出文件
        output_files = list(Path(results_dir).glob("output_*.jsonl"))
        if not output_files:
            return f"處理完成，但未找到輸出文件\n\n日志輸出:\n{log_text}", "", None, None
        
        # 讀取JSONL文件
        output_file = output_files[0]
        with open(output_file, "r") as f:
            content = f.read().strip()
            if not content:
                return f"輸出文件為空\n\n日志輸出:\n{log_text}", "", None, None
            
            # 解析JSON
            result = json.loads(content)
            extracted_text = result.get("text", "未找到文本內容")
            
            # 生成HTML預覽
            try:
                preview_cmd = ["python", "-m", "olmocr.viewer.dolmaviewer", str(output_file)]
                subprocess.run(preview_cmd, check=True)
            except Exception as e:
                log_text += f"\n生成HTML預覽失敗: {str(e)}"
            
            # 查找HTML文件
            html_files = list(Path("dolma_previews").glob("*.html"))
            html_content = ""
            if html_files:
                try:
                    with open(html_files[0], "r", encoding="utf-8") as hf:
                        html_content = hf.read()
                        # 修改HTML以更好地顯示
                        html_content = modify_html_for_better_display(html_content)
                except Exception as e:
                    log_text += f"\n讀取HTML預覽失敗: {str(e)}"
            
            # 創建元數據表格
            metadata = result.get("metadata", {})
            meta_rows = []
            for key, value in metadata.items():
                meta_rows.append([key, value])
            
            df = pd.DataFrame(meta_rows, columns=["屬性", "值"])
            
            return log_text, extracted_text, html_content, df
        
    except subprocess.CalledProcessError as e:
        return f"命令執行失敗: {e.stderr}", "", None, None
    except Exception as e:
        return f"處理過程中發生錯誤: {str(e)}", "", None, None

# 創建Gradio界面
with gr.Blocks(title="olmOCR PDF提取工具") as app:
    gr.Markdown("# olmOCR PDF文本提取工具")
    
    with gr.Row():
        with gr.Column(scale=1):
            pdf_input = gr.File(label="上傳PDF文件", fileemek_types=[".pdf"])
            process_btn = gr.Button("處理PDF", variant="primary")
        
        with gr.Column(scale=2):
            tabs = gr.Tabs()
            with tabs:
                with gr.TabItem("提取文本"):
                    text_output = gr.Textbox(label="提取的文本", lines=20, interactive=True)
                with gr.TabItem("HTML預覽", id="html_preview_tab"):
                    # 使用更大的HTML組件
                    html_output = gr.HTML(label="HTML預覽", elem_id="html_preview_container")
                with gr.TabItem("元數據"):
                    meta_output = gr.DataFrame(label="文檔元數據")
                with gr.TabItem("日誌"):
                    log_output = gr.Textbox(label="處理日誌", lines=15, interactive=False)
    
    # 使用CSS自定義HTML預覽標籤頁和內容大小
    gr.HTML("""
    <style>
    #html_preview_container {
        height: 800px;
        width: 100%; 
        overflow: auto;
        border: 1px solid #ddd;
        border-radius: 4px;
    }
    #html_preview_container iframe {
        width: 100%;
        height: 100%;
        border: none;
    }
    </style>
    """)
    
    # 添加操作說明
    gr.Markdown("""
    ## 使用說明
    1. 上傳PDF文件
    2. 點擊"處理PDF"按鈕
    3. 等待處理完成
    4. 查看提取的文本和HTML預覽
    
    ### 關於HTML預覽
    - HTML預覽展示原始PDF頁面和提取的文本對照
    - 可以清楚地看到OCR過程的精確度
    - 如果預覽內容太小，可以使用右下角的放大/縮小按鈕調整
    
    ## 注意
    - 處理過程可能需要幾分鐘，請耐心等待
    - 首次運行會下載模型（約7GB）
    """)
    
    # 綁定按鈕事件 - 使用阻塞模式
    process_btn.click(
        fn=process_pdf,
        inputs=pdf_input,
        outputs=[log_output, text_output, html_output, meta_output],
        api_name="process"
    )

# 啟動應用
if __name__ == "__main__":
    app.launch(server_name="0.0.0.0", server_port=7860)