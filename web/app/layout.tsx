export const metadata = {
  title: '量化交易分析系统',
  description: '基于技术指标的趋势交易分析工具',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
