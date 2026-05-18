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
        "Stack esperada: React (TypeScript ou JavaScript) — web (Vite/CRA/Next.js).\n"
        "Sinais de aderência (verifique no código fornecido):\n"
        "  • package.json com dependência \"react\" e \"react-dom\";\n"
        "  • entrypoint src/main.tsx|jsx renderizando <App/> em #root;\n"
        "  • componentes funcionais em src/components/ usando hooks (useState, useEffect);\n"
        "  • roteamento (react-router-dom OU app/ router do Next);\n"
        "  • tsconfig.json se a linguagem alvo for TypeScript;\n"
        "  • organização por features/components/hooks/services.\n"
        "Anti-sinais (reduzir nota / gate):\n"
        "  • package.json sem \"react\" → não é React;\n"
        "  • dependência \"react-native\" no package.json → é React Native, não React web;\n"
        "  • somente backend (manage.py, FastAPI, Express isolado);\n"
        "  • só arquivos .py.\n"
        "Critérios técnicos a observar:\n"
        "  • componentização (componentes pequenos e reutilizáveis);\n"
        "  • separação UI / lógica (hooks customizados, services);\n"
        "  • tipagem TS quando aplicável (props, retornos);\n"
        "  • chamadas HTTP isoladas em services/api;\n"
        "  • tratamento de loading/erro;\n"
        "  • acessibilidade básica e estrutura semântica."
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
        "Stack esperada: React Native (TypeScript ou JavaScript), tipicamente com Expo.\n"
        "Sinais de aderência:\n"
        "  • package.json com \"react-native\" (e \"expo\" se Expo);\n"
        "  • app.json / app.config.* (Expo) ou metro.config.js;\n"
        "  • entrypoint App.tsx|jsx OU app/_layout.tsx (Expo Router);\n"
        "  • componentes usam <View>, <Text>, <ScrollView> (react-native), não <div>/<p>;\n"
        "  • navegação via @react-navigation/* ou expo-router.\n"
        "Anti-sinais (gate):\n"
        "  • dependência \"react-dom\" sem \"react-native\" → é React web, não RN;\n"
        "  • uso de <div>, <span>, window/document → não é RN;\n"
        "  • só backend → gate de tipo de aplicação.\n"
        "Critérios técnicos a observar:\n"
        "  • separação por telas (screens/) e componentes (components/);\n"
        "  • navegação organizada;\n"
        "  • hooks customizados, serviços de API isolados;\n"
        "  • uso correto de StyleSheet, SafeAreaView e responsividade;\n"
        "  • tratamento de plataforma (Platform.OS) quando relevante;\n"
        "  • tipagem TS de props e estados quando aplicável."
    ),
)
