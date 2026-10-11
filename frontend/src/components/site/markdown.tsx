import ReactMarkdown from "react-markdown";

/**
 * Markdown из редактора репетитора. Сырой HTML не выводится (нет `rehype-raw`),
 * а стандартный `urlTransform` убирает ссылки `javascript:`.
 */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="space-y-4 leading-relaxed [&_a]:text-primary [&_a]:underline [&_a]:underline-offset-4 [&_ol]:list-decimal [&_ol]:pl-6 [&_ul]:list-disc [&_ul]:pl-6">
      <ReactMarkdown
        // Картинки не выводим: внешний <img> раскрывал бы IP посетителя (alt-текст пропадает).
        disallowedElements={["img"]}
        unwrapDisallowed
        components={{
          // На странице один <h1> (hero), поэтому заголовки текста начинаются с <h3>.
          h1: ({ node, ...props }) => {
            void node;
            return <h3 {...props} />;
          },
          h2: ({ node, ...props }) => {
            void node;
            return <h3 {...props} />;
          },
          a: ({ node, ...props }) => {
            void node;
            return <a {...props} rel="noopener noreferrer" />;
          },
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
