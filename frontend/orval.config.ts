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
        tags: {
          // /admin/* — Auth0 Bearer token, no chat cookie (src/api/adminMutator.ts)
          admin: {
            mutator: {
              path: 'src/api/adminMutator.ts',
              name: 'adminMutator',
            },
          },
        },
        query: {
          useQuery: true,
        },
      },
    },
  },
})
