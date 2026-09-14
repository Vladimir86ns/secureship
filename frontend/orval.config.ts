import { defineConfig } from 'orval'

export default defineConfig({
  secureship: {
    input: {
      target: process.env.OPENAPI_URL || 'http://localhost:8000/openapi.json',
    },
    output: {
      mode: 'tags-split',
      target: 'src/api/generated',
      schemas: 'src/api/generated/models',
      client: 'react-query',
      httpClient: 'axios',
      override: {
        mutator: {
          path: 'src/api/mutator.ts',
          name: 'apiMutator',
        },
        query: {
          useQuery: true,
        },
      },
    },
  },
})
