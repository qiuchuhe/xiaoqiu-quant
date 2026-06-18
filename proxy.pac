function FindProxyForURL(url, host) {
  // 国内域名直连
  if (dnsDomainIs(host, ".cn") ||
      dnsDomainIs(host, ".com.cn") ||
      dnsDomainIs(host, ".net.cn") ||
      dnsDomainIs(host, ".org.cn") ||
      shExpMatch(host, "*.gov.cn") ||
      shExpMatch(host, "*.edu.cn") ||
      dnsDomainIs(host, "qt.gtimg.cn") ||
      dnsDomainIs(host, "yooku.cc") ||
      dnsDomainIs(host, "yhdm.wang") ||
      dnsDomainIs(host, "yhdm.tv") ||
      dnsDomainIs(host, "bilibili.com") ||
      dnsDomainIs(host, "qq.com") ||
      dnsDomainIs(host, "baidu.com") ||
      dnsDomainIs(host, "taobao.com") ||
      dnsDomainIs(host, "jd.com") ||
      dnsDomainIs(host, "weibo.com") ||
      dnsDomainIs(host, "zhihu.com") ||
      dnsDomainIs(host, "163.com") ||
      dnsDomainIs(host, "sina.com.cn") ||
      dnsDomainIs(host, "aliyun.com") ||
      dnsDomainIs(host, "tencent.com") ||
      dnsDomainIs(host, "eastmoney.com") ||
      dnsDomainIs(host, "sina.com") ||
      dnsDomainIs(host, "sohu.com") ||
      isPlainHostName(host) ||
      shExpMatch(host, "10.*") ||
      shExpMatch(host, "172.16.*") ||
      shExpMatch(host, "192.168.*") ||
      shExpMatch(host, "127.*")) {
    return "DIRECT";
  }
  // 国外走代理
  return "PROXY 127.0.0.1:7890";
}
