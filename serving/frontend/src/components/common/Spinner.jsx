import './Spinner.css'

function Spinner({ size = 'md' }) {
  return <div className={`spinner spinner-${size}`} />
}

export default Spinner
