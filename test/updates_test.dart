import "package:flutter_test/flutter_test.dart";
import "package:sonora/core/updates.dart";

const atomXml = '<feed xmlns="http://www.w3.org/2005/Atom">'
    '<title>Sonora Releases</title>'
    '<entry><title>v2.1.0</title>'
    '<link href="https://github.com/songboxiang/sonora/releases/tag/v2.1.0"/>'
    '<content type="html">release one&lt;br/&gt;release two</content></entry>'
    '<entry><title>v2.0.18</title><content>older notes</content></entry>'
    '</feed>';

const rssXml = '<rss><channel><item>'
    '<title><![CDATA[/squeezelite/osx/m1/Squeezelite-M1-2.0.0r1610.dmg]]></title>'
    '<link>https://sourceforge.net/projects/lmsclients/files/squeezelite/osx/m1/Squeezelite-M1-2.0.0r1610.dmg/download</link>'
    '<media:content filesize="2444887" url="https://sourceforge.net/x"/>'
    '<media:hash algo="md5">81d0419b74c0c0f30823ac59a9fcf7a1</media:hash>'
    '</item><item>'
    '<title><![CDATA[/squeezelite/osx/m1/Squeezelite-M1-2.0.0r1595.dmg]]></title>'
    '<link>https://sourceforge.net/old/download</link>'
    '</item><item><title><![CDATA[README.txt]]></title></item>'
    '</channel></rss>';

const sumsText = '592da3254ac0530dd3d1e7d45d76311ffffa8a11e48865ec6830bffb850793a4  Sonora-2.1.0.zip\n'
    '579a56e028400ac99df8dd2abd67089d44e5f5e04eda7020bcfbd9e274bfb826  Sonora-2.1.0.dmg\n';

void main() {
  group("主体版本与发布说明", () {
    test("取 atom 里第一个版本条目，跳过 feed 标题", () {
      expect(parseReleaseVersion(atomXml), "v2.1.0");
    });
    test("发布说明只取最新 entry 且解码 HTML 实体", () {
      final notes = parseReleaseNotes(atomXml, max: 8);
      expect(notes, contains("release one"));
      expect(notes, isNot(contains("older notes")));
    });
    test("无版本时返回 null", () {
      expect(parseReleaseVersion('<feed><title>no releases</title></feed>'), isNull);
    });
  });

  group("核心 RSS 解析", () {
    test("解析最新 dmg 的版本/revision/md5/size/url", () {
      final a = parseCoreRss(rssXml)!;
      expect(a.version, "2.0.0");
      expect(a.revision, 1610);
      expect(a.displayVersion, "2.0.0.r1610");
      expect(a.md5, "81d0419b74c0c0f30823ac59a9fcf7a1");
      expect(a.size, 2444887);
      expect(a.url, contains("r1610.dmg/download"));
      expect(a.filename, "Squeezelite-M1-2.0.0r1610.dmg");
    });
    test("跳过非 dmg 条目", () {
      expect(parseCoreRss(rssXml)!.filename, isNot(contains("README")));
    });
    test("版本名解析兼容 2.0.0-1488 形式", () {
      final a = parseCoreRss(rssXml.replaceFirst("r1610.dmg", "-1488.dmg"))!;
      expect(a.version, "2.0.0");
      expect(a.revision, 1488);
    });
    test("无有效 dmg 时返回 null", () {
      expect(parseCoreRss("<rss><item><title>README.txt</title></item></rss>"), isNull);
    });
  });

  group("SHA256SUMS 与 hash 校验", () {
    test("解析文件名与 hash", () {
      final m = parseSha256Sums(sumsText);
      expect(m["Sonora-2.1.0.zip"],
          "592da3254ac0530dd3d1e7d45d76311ffffa8a11e48865ec6830bffb850793a4");
      expect(m.length, 2);
    });
    test("hash 与 size 一致时通过", () {
      expect(hashMatches(
        actualHash: "ABC123", expectedHash: "abc123",
        actualSize: 100, expectedSize: 100,
      ), isTrue);
    });
    test("size 不符时拒绝", () {
      expect(hashMatches(
        actualHash: "abc123", expectedHash: "abc123",
        actualSize: 99, expectedSize: 100,
      ), isFalse);
    });
    test("hash 不符时拒绝", () {
      expect(hashMatches(actualHash: "x", expectedHash: "y"), isFalse);
    });
    test("没有期望 hash 时一律拒绝", () {
      expect(hashMatches(actualHash: "abc", expectedHash: ""), isFalse);
    });
  });
}
