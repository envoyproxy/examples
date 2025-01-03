import {ChakraProvider, extendTheme} from '@chakra-ui/react'
import {useReducer} from 'react'
import {BrowserRouter as Router, Route, Routes} from "react-router-dom"

import Auth from "./components/Auth"
import Home from "./components/Home"
import Login from "./components/Login"
import Logout from "./components/Logout"
import {AuthContext, DataContext} from "./context"
import {dataInitialState, dataReducer, userInitialState, userReducer} from "./store/reducer"

const theme = extendTheme({
  colors: {
    primary: {
      500: '#000',
    },
  },
})

function App() {
  const [userState, userDispatch] = useReducer(userReducer, userInitialState)
  const [dataState, dataDispatch] = useReducer(dataReducer, dataInitialState)
  return (
    <ChakraProvider theme={theme}>
      <AuthContext.Provider
        value={{
          state: userState,
          dispatch: userDispatch
        }}>
        <DataContext.Provider
          value={{
            state: dataState,
            dispatch: dataDispatch
          }}>
          <Router>
            <Routes>
              <Route
                path="/authorize"
                element={<Auth />}/>
              <Route
                path="/login"
                element={<Login />}/>
              <Route
                path="/logout"
                element={<Logout />}/>
              <Route
                path="/"
                element={<Home />}/>
            </Routes>
          </Router>
        </DataContext.Provider>
      </AuthContext.Provider>
    </ChakraProvider>
  )
}

export default App
