# 示例脚本｜本仓库所有数据均为合成演示数据，不对应任何真实研究结果。
# 运行需要 R；工作台只登记路径，不执行代码。

df <- read.csv("results/summary.csv", stringsAsFactors = FALSE)
x <- subset(df, group == "A")$log2CPM
y <- subset(df, group == "B")$log2CPM
test <- wilcox.test(x, y, conf.int = TRUE, exact = FALSE)
cat("median A/B:", median(x), median(y), "\n")
print(test)
svg("figures/primary_boxplot.svg", width = 6, height = 4.5)
boxplot(log2CPM ~ group, data = df, outline = FALSE,
        names = c("Group A (n=10)", "Group B (n=10)"),
        ylab = "log2CPM", main = "Primary analysis (synthetic data)")
stripchart(log2CPM ~ group, data = df, method = "jitter",
           vertical = TRUE, add = TRUE, pch = 19, col = "#8C5B48")
dev.off()
