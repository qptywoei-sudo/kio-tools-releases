#include "LanguagePolicy.h"
#include <cassert>
int main() {
 using KioLanguage::normalize;
 assert(normalize("zh-CN")=="zh-CN");assert(normalize("zh-SG")=="zh-CN");
 assert(normalize("zh-Hans-TW")=="zh-CN");assert(normalize("zh")=="zh-CN");
 assert(normalize("zh-TW")=="zh-TW");assert(normalize("zh-HK")=="zh-TW");
 assert(normalize("zh-MO")=="zh-TW");assert(normalize("zh-Hant-CN")=="zh-TW");
 assert(normalize(" ZH_hant_HK ")=="zh-TW");assert(normalize("ko-KR")=="ko");
 assert(normalize("en-US")=="en");assert(normalize("en-GB")=="en");
 assert(normalize("vi-VN")=="vi");assert(normalize("ja-JP")=="ja");
 assert(normalize("fr-FR").empty());assert(normalize("").empty());
 for(int i=0;i<6;i++)assert(KioLanguage::index(KioLanguage::codes[i])==i);
 assert(KioLanguage::index("unsupported")==1);
}
