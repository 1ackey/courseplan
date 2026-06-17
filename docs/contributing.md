# 贡献指南

欢迎为英语学院课程信息平台贡献课程内容！每一次贡献都能帮助更多同学在选课前了解课程。

## 贡献方式

### 准备工作

1. **Fork 本仓库** → GitHub 仓库页面点击 Fork 按钮
2. **Clone 到本地** → `git clone https://github.com/your-username/courseplan.git`
3. **安装依赖** → `pip install -r requirements.txt`

### 添加课程

1. 复制课程模板：
   ```
   cp docs/templates/course-template.md docs/categories/<类别>/<课程代码>.md
   ```

   类别与目录对应关系：

   | 课程类别 | 目录 |
   |----------|------|
   | 基础必修 | `docs/categories/basic-required/` |
   | 基础选修 | `docs/categories/basic-elective/` |
   | 专业方向课 | `docs/categories/major-direction/` |
   | 实验课 | `docs/categories/lab/` |

2. 打开文件，按照模板填写课程信息：
   - 课程基本信息（名称、代码、教师、课时等）
   - 考核方式
   - 教材及参考资料（选填）
   - 教学进度表（按周教学内容）

3. 本地预览：
   ```
   mkdocs serve
   ```
   浏览器打开 `http://127.0.0.1:8000` 查看效果

4. 提交 PR：
   ```
   git add .
   git commit -m "添加课程: ENG820 语用学"
   git push origin main
   ```
   然后在 GitHub 上创建 Pull Request。

### 信息源要求

- **必须基于教师发放的教学进度表**，确保信息准确
- 考核方式如进度表中未包含，请向教师或学长学姐确认后补充
- 请在文件末尾标注信息来源（学年、学期）

### PR 检查

提交 PR 后，GitHub Actions 会自动检查：
- Markdown 格式是否正确
- 必填字段是否完整
- 站点是否能正常构建

如果检查失败，请根据 PR 评论区提示修改后重新提交。

### 更新已有课程

如果某门课程信息过时（如换了教师、更新了考核方式），直接编辑对应的 Markdown 文件提交 PR 即可。

---

有问题？[提交 Issue](https://github.com/SIS-UIBE/courseplan/issues)
