from app.profiles.base import ProjectProfile

REACT_PROFILE = ProjectProfile(
    name="react",
    canonical_language="React (web) — TypeScript ou JavaScript",
    aliases=[
        "react",
        "reactjs",
        "react.js",
        "typescript react",
        "ts react",
        "javascript react",
        "js react",
        "react typescript",
        "react javascript",
    ],
    tech_stack=[
        "react (package.json: \"react\" + \"react-dom\")",
        "typescript (.ts/.tsx) ou javascript (.js/.jsx)",
        "entrypoint: src/main.tsx|jsx ou app/ (Next.js)",
        "bundler: vite, next ou cra",
    ],
    detection_globs=[
        "**/package.json",
        "**/vite.config.*",
        "**/next.config.*",
        "**/index.html",
    ],
    hint_globs=[
        "**/tsconfig.json",
        "**/.eslintrc*",
        "**/tailwind.config.*",
    ],
    include_globs=[
        # Manifestos / configuração
        "package.json",
        "tsconfig.json",
        "jsconfig.json",
        "vite.config.*",
        "next.config.*",
        "tailwind.config.*",
        "postcss.config.*",
        ".env.example",
        "index.html",
        # App e entrypoint
        "**/src/main.tsx",
        "**/src/main.jsx",
        "**/src/main.ts",
        "**/src/main.js",
        "**/src/App.tsx",
        "**/src/App.jsx",
        "**/src/index.tsx",
        "**/src/index.jsx",
        # Estrutura típica
        "**/src/**/*.tsx",
        "**/src/**/*.ts",
        "**/src/**/*.jsx",
        "**/src/**/*.js",
        "**/src/**/*.css",
        "**/src/**/*.scss",
        # Next.js (app/pages router)
        "**/app/**/*.tsx",
        "**/app/**/*.ts",
        "**/pages/**/*.tsx",
        "**/pages/**/*.ts",
        # Pastas convencionais
        "**/components/**/*.tsx",
        "**/components/**/*.jsx",
        "**/hooks/**/*.ts",
        "**/hooks/**/*.tsx",
        "**/contexts/**/*.tsx",
        "**/contexts/**/*.ts",
        "**/services/**/*.ts",
        "**/services/**/*.tsx",
        "**/api/**/*.ts",
        "**/routes/**/*.tsx",
        "**/routes/**/*.ts",
        "**/store/**/*.ts",
        "**/store/**/*.tsx",
        # Testes
        "**/*.test.tsx",
        "**/*.test.ts",
        "**/*.spec.tsx",
        "**/*.spec.ts",
        "**/README*",
    ],
    exclude_globs=[
        "**/node_modules/**",
        "**/dist/**",
        "**/build/**",
        "**/.next/**",
        "**/.turbo/**",
        "**/.parcel-cache/**",
        "**/coverage/**",
        "**/*.lock",
        "**/package-lock.json",
        "**/pnpm-lock.yaml",
        "**/yarn.lock",
        "**/*.min.js",
        "**/*.min.css",
        "**/public/**/*.{png,jpg,jpeg,gif,svg,ico,webp}",
        "**/.git/**",
    ],
    must_read_globs=[
        "package.json",
        "tsconfig.json",
        "**/src/App.tsx",
        "**/src/App.jsx",
        "**/src/main.tsx",
        "**/src/index.tsx",
    ],
    evaluation_hints=(
        "Stack: React (web) — Vite, CRA ou Next.js, com TypeScript ou JavaScript.\n"
        "\n"
        "REGRAS DE AVALIAÇÃO REACT (use junto com R1–R6 do prompt comum):\n"
        "  R1. \"Componente X existe\" exige `export (default|const|function) X` em arquivo `.tsx`/`.jsx`/`.ts`/`.js`. Importar X em outro arquivo NÃO prova existência.\n"
        "  R2. \"Rota X existe\" exige UMA destas evidências literais: `<Route path='/x' element={X}/>` (react-router), entry em `routes` array, OU arquivo `app/x/page.tsx` / `pages/x.tsx` (Next.js). Sem isso, a rota não está montada.\n"
        "  R3. \"Hook customizado X\" exige função em arquivo (geralmente em `hooks/`) cujo nome COMECE com `use` (ex: `useAuth`) e que chame outros hooks dentro. `function useX()` em components/ ainda conta, mas helper sem `use*` no nome NÃO é hook.\n"
        "  R4. \"Chamada a API X\" exige `fetch(...)` ou cliente HTTP (`axios`, `ky`) em `services/`, `api/` ou hook. Mock/string com URL em comentário NÃO prova chamada real.\n"
        "  R5. \"Gerenciamento de estado global\" exige uma destas: Context API (`createContext` + `<Provider>` montado na árvore), Redux (`configureStore`/`createSlice`), Zustand (`create(...)`), Jotai (`atom`). `useState` local em um componente NÃO é estado global.\n"
        "  R6. \"Tipagem TypeScript\" exige `.ts`/`.tsx` E uso real de tipos (interface/type/props tipadas). Só renomear `.js` → `.tsx` sem tipos NÃO conta.\n"
        "  R7. \"Estilização X\" — verifique a dependência REAL no `package.json`: tailwind (`tailwindcss` + `tailwind.config.*`), styled-components (`styled-components` + ``styled.div`...```), CSS modules (`*.module.css`), MUI (`@mui/material`). Importar nada e usar className não prova framework.\n"
        "  R8. \"Testes\" exige arquivos `*.test.tsx`/`*.spec.tsx` com `describe`/`it`/`test` reais — não basta ter `vitest`/`jest` no package.json.\n"
        "\n"
        "FOCO de leitura (ordem de importância):\n"
        "  1. package.json — confirma dependências reais (R7, R5);\n"
        "  2. src/main.tsx|jsx ou app/layout.tsx — entrypoint;\n"
        "  3. src/App.tsx — estrutura raiz + roteamento (R2);\n"
        "  4. src/components/**, src/pages/**, app/** — componentes (R1) e rotas (R2);\n"
        "  5. src/hooks/** — hooks customizados (R3);\n"
        "  6. src/services/**, src/api/** — chamadas HTTP (R4);\n"
        "  7. src/store/**, src/contexts/** — estado global (R5);\n"
        "  8. tsconfig.json — gate de TypeScript (R6).\n"
        "\n"
        "Anti-sinais que devem aparecer no diagnóstico:\n"
        "  • package.json sem \"react\" → não é React;\n"
        "  • dependência \"react-native\" presente → é React Native, não React web;\n"
        "  • componentes massivos (>300 linhas, múltiplas responsabilidades) → falta componentização;\n"
        "  • lógica de fetch direto em componentes em vez de hooks/services → acoplamento;\n"
        "  • sem tratamento de loading/erro nas chamadas HTTP."
    ),
)


REACT_NATIVE_PROFILE = ProjectProfile(
    name="react-native",
    canonical_language="React Native — TypeScript ou JavaScript (Expo opcional)",
    aliases=[
        "react native",
        "reactnative",
        "rn",
        "typescript react native",
        "ts react native",
        "javascript react native",
        "js react native",
        "expo",
        "react native expo",
    ],
    tech_stack=[
        "react native (package.json: \"react-native\")",
        "expo (opcional: app.json, expo-router) ou CLI puro (android/ + ios/)",
        "typescript (.ts/.tsx) ou javascript (.js/.jsx)",
        "componentes RN: <View>, <Text>, <ScrollView> — NÃO <div>/<span>",
    ],
    detection_globs=[
        "**/app.json",
        "**/app.config.*",
        "**/metro.config.*",
        "**/babel.config.js",
        "**/index.js",
    ],
    hint_globs=[
        "**/package.json",
        "**/tsconfig.json",
        "**/eas.json",
    ],
    include_globs=[
        # Manifestos
        "package.json",
        "tsconfig.json",
        "app.json",
        "app.config.*",
        "metro.config.*",
        "babel.config.*",
        "eas.json",
        ".env.example",
        # Entrypoint
        "index.js",
        "index.ts",
        "App.tsx",
        "App.jsx",
        "App.ts",
        "App.js",
        # Estrutura
        "**/src/**/*.tsx",
        "**/src/**/*.ts",
        "**/src/**/*.jsx",
        "**/src/**/*.js",
        # Expo Router (app/ directory)
        "**/app/**/*.tsx",
        "**/app/**/*.ts",
        # Pastas convencionais RN
        "**/screens/**/*.tsx",
        "**/screens/**/*.ts",
        "**/screens/**/*.jsx",
        "**/components/**/*.tsx",
        "**/components/**/*.jsx",
        "**/components/**/*.ts",
        "**/navigation/**/*.tsx",
        "**/navigation/**/*.ts",
        "**/hooks/**/*.ts",
        "**/hooks/**/*.tsx",
        "**/contexts/**/*.tsx",
        "**/contexts/**/*.ts",
        "**/services/**/*.ts",
        "**/api/**/*.ts",
        "**/store/**/*.ts",
        "**/store/**/*.tsx",
        # Testes
        "**/*.test.tsx",
        "**/*.test.ts",
        "**/__tests__/**/*.{ts,tsx,js,jsx}",
        "**/README*",
    ],
    exclude_globs=[
        "**/node_modules/**",
        "**/android/build/**",
        "**/android/.gradle/**",
        "**/android/app/build/**",
        "**/ios/Pods/**",
        "**/ios/build/**",
        "**/.expo/**",
        "**/.expo-shared/**",
        "**/dist/**",
        "**/build/**",
        "**/coverage/**",
        "**/*.lock",
        "**/package-lock.json",
        "**/pnpm-lock.yaml",
        "**/yarn.lock",
        "**/*.min.js",
        "**/assets/**/*.{png,jpg,jpeg,gif,svg,ico,webp,ttf,otf}",
        "**/.git/**",
    ],
    must_read_globs=[
        "package.json",
        "app.json",
        "App.tsx",
        "App.jsx",
        "index.js",
        "tsconfig.json",
    ],
    evaluation_hints=(
        "Stack: React Native (TypeScript ou JavaScript), tipicamente com Expo (Expo Router OU CLI puro).\n"
        "\n"
        "REGRAS DE AVALIAÇÃO REACT NATIVE (use junto com R1–R6 do prompt comum):\n"
        "  RN1. Confirmar que É React Native (não React web): package.json TEM `react-native` como dependência. Se só tem `react-dom`, é web — emita gate.\n"
        "  RN2. \"Componente X existe\" exige `export (default|const|function) X` em `.tsx`/`.jsx` que retorna JSX usando primitives RN (`<View>`, `<Text>`, `<ScrollView>`, `<TouchableOpacity>`, etc.). Componente retornando `<div>`/`<span>` NÃO é RN — é código web copiado.\n"
        "  RN3. \"Tela X existe\" exige arquivo em `screens/`, `app/` (Expo Router) ou registrado num Stack/Tab Navigator. Componente solto em `components/` não é tela.\n"
        "  RN4. \"Navegação configurada\" exige UMA destas: `@react-navigation/native` com `<NavigationContainer>` + `createStackNavigator`/`createBottomTabNavigator`; OU `expo-router` com `app/_layout.tsx`. Importar sem montar NÃO conta.\n"
        "  RN5. \"Hook customizado X\" exige função nomeada `useX` (em `hooks/`) que chame outros hooks. Helper sem prefixo `use` NÃO é hook.\n"
        "  RN6. \"Chamada a API X\" exige `fetch(...)` ou cliente HTTP (`axios`, `ky`) em `services/`, `api/` ou hook. String com URL em comentário ou mock NÃO prova.\n"
        "  RN7. \"Estilização\" — em RN, estilo é via `StyleSheet.create({...})` ou `style={{...}}` inline. NÃO use CSS files: arquivos `.css` em projeto RN são bandeira vermelha (provavelmente código web copiado).\n"
        "  RN8. \"Estado global\" exige Context+Provider, Redux (`configureStore`), Zustand (`create`) ou Jotai (`atom`). `useState` em uma tela NÃO é estado global.\n"
        "  RN9. \"Tipagem TypeScript\" exige `.tsx`/`.ts` E props/state realmente tipados (interface/type). Só renomear `.js` → `.tsx` sem tipos NÃO conta.\n"
        "  RN10. \"Suporte a plataforma\" — se o critério pede comportamento por plataforma, exige `Platform.OS === 'ios'`/`'android'` ou arquivos `.ios.tsx`/`.android.tsx`. Sem isso, é código único para todas as plataformas.\n"
        "\n"
        "FOCO de leitura (ordem de importância):\n"
        "  1. package.json — confirma `react-native` (RN1) e libs (navegação RN4, estado RN8);\n"
        "  2. App.tsx / index.js / app/_layout.tsx — entrypoint e raiz de navegação (RN4);\n"
        "  3. screens/** ou app/** — telas (RN3);\n"
        "  4. components/** — componentes (RN2);\n"
        "  5. navigation/** — Stack/Tab Navigator (RN4);\n"
        "  6. hooks/** — hooks customizados (RN5);\n"
        "  7. services/**, api/** — chamadas HTTP (RN6);\n"
        "  8. app.json / app.config.* — configuração Expo;\n"
        "  9. tsconfig.json — gate de TS (RN9).\n"
        "\n"
        "Anti-sinais que devem aparecer no diagnóstico:\n"
        "  • `react-dom` em deps sem `react-native` → é React web (gate, profile errado);\n"
        "  • uso de `<div>`/`<span>`/`window`/`document`/`localStorage` no código → não é RN puro;\n"
        "  • arquivos `.css`/`.scss` no projeto → padrão web infiltrado;\n"
        "  • telas sem `SafeAreaView` ou `ScrollView` (UX de mobile);\n"
        "  • chamadas HTTP direto nas telas em vez de hooks/services → acoplamento."
    ),
)
