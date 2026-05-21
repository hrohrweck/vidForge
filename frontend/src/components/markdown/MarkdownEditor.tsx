import { useState, useCallback } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import Link from '@tiptap/extension-link'
import { Table } from '@tiptap/extension-table'
import { TableRow } from '@tiptap/extension-table-row'
import { TableCell } from '@tiptap/extension-table-cell'
import { TableHeader } from '@tiptap/extension-table-header'
import { Bold, Italic, List, ListOrdered, Quote, Code, Link as LinkIcon, Image as ImageIcon, Table as TableIcon, Eye, Edit3 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface MarkdownEditorProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
}

export function MarkdownEditor({ value, onChange, placeholder }: MarkdownEditorProps) {
  const [isRawMode, setIsRawMode] = useState(false)
  const [rawValue, setRawValue] = useState(value)

  const editor = useEditor({
    extensions: [
      StarterKit,
      Image,
      Link.configure({
        openOnClick: false,
      }),
      Table.configure({
        resizable: true,
      }),
      TableRow,
      TableCell,
      TableHeader,
    ],
    content: value,
    onUpdate: ({ editor }) => {
      onChange(editor.getHTML())
    },
  })

  const handleRawChange = useCallback((newValue: string) => {
    setRawValue(newValue)
    onChange(newValue)
  }, [onChange])

  if (!editor) {
    return null
  }

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      {/* Toolbar */}
      <div className="border-b border-border p-2 flex items-center gap-1 flex-wrap">
        <div className="flex items-center gap-1">
          <button
            onClick={() => editor.chain().focus().toggleBold().run()}
            className={`p-1.5 rounded hover:bg-muted ${editor.isActive('bold') ? 'bg-secondary' : ''}`}
          >
            <Bold className="h-4 w-4" />
          </button>
          <button
            onClick={() => editor.chain().focus().toggleItalic().run()}
            className={`p-1.5 rounded hover:bg-muted ${editor.isActive('italic') ? 'bg-secondary' : ''}`}
          >
            <Italic className="h-4 w-4" />
          </button>
          <button
            onClick={() => editor.chain().focus().toggleBulletList().run()}
            className={`p-1.5 rounded hover:bg-muted ${editor.isActive('bulletList') ? 'bg-secondary' : ''}`}
          >
            <List className="h-4 w-4" />
          </button>
          <button
            onClick={() => editor.chain().focus().toggleOrderedList().run()}
            className={`p-1.5 rounded hover:bg-muted ${editor.isActive('orderedList') ? 'bg-secondary' : ''}`}
          >
            <ListOrdered className="h-4 w-4" />
          </button>
          <button
            onClick={() => editor.chain().focus().toggleBlockquote().run()}
            className={`p-1.5 rounded hover:bg-muted ${editor.isActive('blockquote') ? 'bg-secondary' : ''}`}
          >
            <Quote className="h-4 w-4" />
          </button>
          <button
            onClick={() => editor.chain().focus().toggleCodeBlock().run()}
            className={`p-1.5 rounded hover:bg-muted ${editor.isActive('codeBlock') ? 'bg-secondary' : ''}`}
          >
            <Code className="h-4 w-4" />
          </button>
          <button
            onClick={() => {
              const url = window.prompt('Enter URL:')
              if (url) {
                editor.chain().focus().setLink({ href: url }).run()
              }
            }}
            className={`p-1.5 rounded hover:bg-muted ${editor.isActive('link') ? 'bg-secondary' : ''}`}
          >
            <LinkIcon className="h-4 w-4" />
          </button>
          <button
            onClick={() => {
              const url = window.prompt('Enter image URL:')
              if (url) {
                editor.chain().focus().setImage({ src: url }).run()
              }
            }}
            className="p-1.5 rounded hover:bg-muted"
          >
            <ImageIcon className="h-4 w-4" />
          </button>
          <button
            onClick={() => editor.chain().focus().insertTable({ rows: 3, cols: 3 }).run()}
            className="p-1.5 rounded hover:bg-muted"
          >
            <TableIcon className="h-4 w-4" />
          </button>
        </div>

        <div className="ml-auto flex items-center gap-1">
          <button
            onClick={() => {
              if (isRawMode) {
                editor.commands.setContent(rawValue)
              } else {
                setRawValue(editor.getHTML())
              }
              setIsRawMode(!isRawMode)
            }}
            className="flex items-center gap-1 px-2 py-1 text-sm rounded hover:bg-muted"
          >
            {isRawMode ? <Edit3 className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            {isRawMode ? 'WYSIWYG' : 'Raw'}
          </button>
        </div>
      </div>

      {/* Editor Content */}
      <div className="p-4 min-h-[200px]">
        {isRawMode ? (
          <textarea
            value={rawValue}
            onChange={(e) => handleRawChange(e.target.value)}
            className="w-full h-full min-h-[200px] resize-y font-mono text-sm p-2 border rounded"
            placeholder={placeholder}
          />
        ) : (
          <EditorContent
            editor={editor}
            className="prose prose-sm max-w-none"
          />
        )}
      </div>

      {/* Preview (shown in raw mode) */}
      {isRawMode && rawValue && (
        <div className="border-t border-border p-4 bg-muted/50">
          <h4 className="text-sm font-semibold text-muted-foreground mb-2">Preview</h4>
          <div className="prose prose-sm max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {rawValue}
            </ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  )
}
