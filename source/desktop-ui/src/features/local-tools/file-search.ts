import type {ToolLanguage} from './types';

export type FileSearchFilters={extensions?:string[];dateFrom?:string;dateTo?:string;path?:string};
export type FileSearchPreview={id:string;name:string;size:number;extension:string;modified:string;path:string;kind:'pdf'|'document'|'spreadsheet'|'presentation'|'text'|'image'|'binary';text:string;truncated:boolean;pages?:number};
export function fileSearchFilters(extensions:string,dateFrom='',dateTo='',path=''):FileSearchFilters{
 const values=extensions.split(/[\s,;]+/).filter(Boolean);
 if(values.length>20||values.some(value=>!/^\.?[a-zA-Z0-9]{1,16}$/.test(value))||path.length>1000||path.includes('\0'))throw Error('invalidRequest');
 for(const date of [dateFrom,dateTo])if(date&&(!/^\d{4}-\d{2}-\d{2}$/.test(date)||Number.isNaN(Date.parse(date+'T00:00:00Z'))||new Date(date+'T00:00:00Z').toISOString().slice(0,10)!==date))throw Error('invalidRequest');
 if(dateFrom&&dateTo&&dateFrom>dateTo)throw Error('invalidRequest');
 return {...(values.length?{extensions:[...new Set(values.map(value=>'.'+value.replace(/^\./,'').toLowerCase()))]}:{}),...(dateFrom?{dateFrom}:{}),...(dateTo?{dateTo}:{}),...(path.trim()?{path:path.trim()}:{})};
}
const words={
 ko:{extensionExample:'예: pdf, docx, xlsx, txt',extension:'확장자',from:'수정 날짜부터',to:'수정 날짜까지',path:'경로',modified:'수정 날짜',size:'크기',stopIndex:'색인 중지',indexCancelled:'색인 중지됨',emptyPreview:'추출할 수 있는 텍스트가 없습니다. 원본 파일을 열어 확인하세요.',truncated:'처음 20,000자만 표시합니다.',pages:'페이지'},
 en:{extensionExample:'For example: pdf, docx, xlsx, txt',extension:'Extensions',from:'Modified from',to:'Modified through',path:'Path',modified:'Modified',size:'Size',stopIndex:'Stop indexing',indexCancelled:'Indexing stopped',emptyPreview:'No extractable text. Open the original file to view it.',truncated:'Showing the first 20,000 characters.',pages:'Pages'},
 vi:{extensionExample:'Ví dụ: pdf, docx, xlsx, txt',extension:'Phần mở rộng',from:'Sửa từ ngày',to:'Sửa đến ngày',path:'Đường dẫn',modified:'Ngày sửa',size:'Kích thước',stopIndex:'Dừng lập chỉ mục',indexCancelled:'Đã dừng lập chỉ mục',emptyPreview:'Không có văn bản trích xuất được. Mở tệp gốc để xem.',truncated:'Hiển thị 20.000 ký tự đầu.',pages:'Trang'},
 ja:{extensionExample:'例: pdf, docx, xlsx, txt',extension:'拡張子',from:'更新日から',to:'更新日まで',path:'パス',modified:'更新日',size:'サイズ',stopIndex:'索引作成を停止',indexCancelled:'索引作成を停止しました',emptyPreview:'抽出できるテキストがありません。元のファイルを開いてください。',truncated:'最初の20,000文字を表示しています。',pages:'ページ'},
 zh:{extensionExample:'例如：pdf、docx、xlsx、txt',extension:'扩展名',from:'修改日期起',to:'修改日期止',path:'路径',modified:'修改日期',size:'大小',stopIndex:'停止索引',indexCancelled:'索引已停止',emptyPreview:'没有可提取的文字。请打开原始文件查看。',truncated:'显示前20,000个字符。',pages:'页数'}, "zh-TW":{extensionExample:'例如：pdf、docx、xlsx、txt',extension:'副檔名',from:'修改日期起',to:'修改日期止',path:'路徑',modified:'修改日期',size:'大小',stopIndex:'停止索引',indexCancelled:'索引已停止',emptyPreview:'沒有可提取的文字。請開啟原始檔案檢視。',truncated:'顯示前20,000個字元。',pages:'頁數'}
};
export function fileSearchWords(language:ToolLanguage){return words[language];}

