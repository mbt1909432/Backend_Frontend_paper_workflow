@echo off
chcp 65001 >nul

REM 检查是否提供了提交信息
if "%~1"=="" (
    echo 用法: git-push-msg.bat "你的提交信息"
    echo 示例: git-push-msg.bat "修复bug"
    pause
    exit /b 1
)

echo ====================================
echo Git 自动提交脚本
echo ====================================

git add .
echo [✓] 文件已添加

git commit -m "%~1"
if errorlevel 1 (
    echo [×] 提交失败
    pause
    exit /b 1
)
echo [✓] 提交成功

git push origin main
if errorlevel 1 (
    echo [×] 推送失败
    pause
    exit /b 1
)
echo [✓] 推送成功

echo ====================================
echo 所有操作完成！
echo ====================================
pause