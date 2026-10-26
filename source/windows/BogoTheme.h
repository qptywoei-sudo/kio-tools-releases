#pragma once
#include <windows.h>

// Display chrome only. Document, canvas and recording-status colors stay separate.
namespace BogoTheme {
inline constexpr COLORREF header = RGB(255, 243, 232);
inline constexpr COLORREF background = RGB(255, 250, 246);
inline constexpr COLORREF selection = RGB(255, 231, 212);
inline constexpr COLORREF line = RGB(241, 211, 189);
inline constexpr COLORREF ink = RGB(52, 43, 38);
inline constexpr COLORREF accent = RGB(252, 117, 1);
inline HBRUSH backgroundBrush() { static HBRUSH brush = CreateSolidBrush(background); return brush; }
inline HBRUSH selectionBrush() { static HBRUSH brush = CreateSolidBrush(selection); return brush; }
inline LRESULT controlColor(WPARAM value) {
    HDC dc = reinterpret_cast<HDC>(value);
    SetTextColor(dc, ink); SetBkColor(dc, background);
    return reinterpret_cast<LRESULT>(backgroundBrush());
}
}
