# copy_innovation_synthesis 脚本使用说明

该脚本用于批量收集某个用户在 `app/core/workflows/output/<user_name>` 目录下所有会话生成的 `final_proposals/innovation_synthesis*.md` 文件，并复制到一个集中目录，便于人工查看或归档。

## 运行前提

1. 已按默认结构保存各个 session 的输出：`app/core/workflows/output/<user_name>/session_*/final_proposals/innovation_synthesis*.md`。
2. Python 环境可直接运行项目脚本（例如 `python scripts/...`）。

## 基本用法

```bash
python scripts/copy_innovation_synthesis.py --user-name dev_tester
```

- `--user-name`：必填，对应 `output` 下的用户目录名。
- 默认输出会复制到 `app/core/workflows/output/<user_name>/collected_markdown/`。

## 常用可选参数

```bash
python scripts/copy_innovation_synthesis.py \
    --user-name alice \
    --output-root E:/pycharm_project/software_idea/academic draft agentic_workflow/app/core/workflows/output \
    --dest-dir E:/exports/alice_md
```

- `--output-root`：自定义输出根目录，默认是项目内 `app/core/workflows/output`。
- `--dest-dir`：自定义目标目录；若不填，会自动创建 `<output-root>/<user>/collected_markdown`。

## 运行结果

- 控制台会打印每个被复制的 Markdown 文件的源路径和目标路径。
- 最后输出统计行：`Done. X file(s) copied to <dest_dir>`。
- 如未找到匹配文件，会提示 `No innovation_synthesis markdowns found under ...` 并返回 `0`。

## 常见问题

1. **提示找不到用户目录**  
   检查 `--user-name` 是否与 `output` 下的实际文件夹相同，或使用 `--output-root` 指向正确路径。

2. **最终目录中文件重复覆盖**  
   目标文件名由 `session_xxx` 和原始 Markdown 的 `innovation_synthesis` 后缀拼接生成；若希望完整保留原名，可按需修改脚本中的命名规则。

3. **希望按 session 分类存放**  
   可多次执行脚本并指定不同 `--dest-dir`；或在脚本中根据 `session_name` 创建子目录后再复制。


