#pragma once
#include <string>
namespace WindowsCommandLine {
// CRT argv quoting: double runs of backslashes before quotes and the closing quote.
inline std::wstring quote(const std::wstring&value){std::wstring out=L"\"";size_t slashes=0;for(wchar_t c:value){if(c==L'\\'){++slashes;continue;}if(c==L'\"'){out.append(slashes*2+1,L'\\');out+=c;slashes=0;continue;}out.append(slashes,L'\\');slashes=0;out+=c;}out.append(slashes*2,L'\\');out+=L'\"';return out;}
}
