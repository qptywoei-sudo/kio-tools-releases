#include "PageOrder.h"
#include <cassert>
#include <iostream>
int main(){
 std::vector<int> pages{1,2,3,4,5,6};auto selected=PageOrder::move(pages,{1,2},6);assert((pages==std::vector<int>{1,4,5,6,2,3}));assert((selected==std::vector<int>{4,5}));
 pages={1,2,3,4,5,6};selected=PageOrder::move(pages,{1,3},0);assert((pages==std::vector<int>{2,4,1,3,5,6}));assert((selected==std::vector<int>{0,1}));
 pages={1,2,3,4};selected=PageOrder::move(pages,{1,2},2);assert((pages==std::vector<int>{1,2,3,4}));
 pages={1,2,3,4,5};selected=PageOrder::nudge(pages,{1,2},-1);assert((pages==std::vector<int>{2,3,1,4,5}));assert((selected==std::vector<int>{0,1}));
 selected=PageOrder::nudge(pages,selected,1);assert((pages==std::vector<int>{1,2,3,4,5}));assert((selected==std::vector<int>{1,2}));
 selected=PageOrder::nudge(pages,{0,4},1);assert((pages==std::vector<int>{2,1,3,4,5}));assert((selected==std::vector<int>{1,4}));
 pages={1,2,3};selected=PageOrder::move(pages,{-1,1,1,99},99);assert((pages==std::vector<int>{1,3,2}));assert((selected==std::vector<int>{2}));
 std::vector<int> range;assert(PageOrder::parseRange(std::wstring(L"1-3,5,3"),6,range));assert((range==std::vector<int>{1,2,3,5}));assert(PageOrder::parseRange(std::wstring(L"3; 1\t2"),3,range));assert((range==std::vector<int>{3,1,2}));assert(PageOrder::parseRange(std::wstring(L" \r\n"),3,range));assert((range==std::vector<int>{1,2,3}));for(auto bad:{L"4-2",L"0",L"1-4",L"999999999999999999",L"1x",L"1 -2",L",;"})assert(!PageOrder::parseRange(std::wstring(bad),3,range));
 std::cout<<"PASS: group drop before/after, noncontiguous stable order, no-op drop, grouped up/down, boundaries, invalid/duplicate selection; extraction ranges preserve order, validate bounds and resist numeric overflow\n";
}
